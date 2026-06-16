"""Maintenance runner for generated artifact lifecycle sidecars."""

from __future__ import annotations

import logging
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Protocol

from sqlalchemy import create_engine, text

from app.services.stores.postgres_base import PostgresStoreBase

from .payload_reader import checksum_matches, result_json_path_for_candidate
from .policy import ArtifactLifecycleCandidate, ArtifactLifecyclePolicy
from .summary_sidecar import summary_path_for_candidate

logger = logging.getLogger(__name__)


class LifecycleApplyGate(Protocol):
    """Gate object required before destructive lifecycle apply."""

    def assert_apply_allowed(self) -> None:
        """Raise if the current runtime state cannot safely mutate files."""


@dataclass
class ArtifactLifecycleRunSummary:
    """Aggregate result for one lifecycle maintenance run."""

    examined: int = 0
    keep: int = 0
    remove_summary: int = 0
    missing_result: int = 0
    missing_db_pointer: int = 0
    skipped_active: int = 0
    error: int = 0
    archived_summary: int = 0
    archive_path: Optional[str] = None
    reasons: Dict[str, int] = field(default_factory=dict)

    def mark_reason(self, reason: str) -> None:
        """Increment a decision reason counter."""
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def as_dict(self) -> Dict[str, object]:
        """Return a JSON-friendly summary."""
        return {
            "examined": self.examined,
            "keep": self.keep,
            "remove_summary": self.remove_summary,
            "missing_result": self.missing_result,
            "missing_db_pointer": self.missing_db_pointer,
            "skipped_active": self.skipped_active,
            "error": self.error,
            "archived_summary": self.archived_summary,
            "archive_path": self.archive_path,
            "reasons": dict(sorted(self.reasons.items())),
        }


class ArtifactLifecycleMaintenance:
    """Run bounded dry-run or apply lifecycle maintenance batches."""

    def __init__(
        self,
        *,
        reader: object,
        policy: Optional[ArtifactLifecyclePolicy] = None,
        apply_gate: Optional[LifecycleApplyGate] = None,
    ) -> None:
        self.reader = reader
        self.policy = policy or ArtifactLifecyclePolicy()
        self.apply_gate = apply_gate

    def run(
        self,
        *,
        dry_run: bool = True,
        limit: Optional[int] = None,
        archive_dir: Optional[Path] = None,
    ) -> ArtifactLifecycleRunSummary:
        """Run lifecycle classification and optional summary sidecar removal."""
        if not dry_run:
            if self.apply_gate is None:
                raise RuntimeError("apply requires a lifecycle apply gate")
            self.apply_gate.assert_apply_allowed()

        summary = ArtifactLifecycleRunSummary()
        removal_paths: List[Path] = []
        for candidate in self._iter_candidates(limit=limit):
            self._classify_candidate(candidate, summary, removal_paths)

        if dry_run or not removal_paths:
            return summary

        if archive_dir is None:
            raise RuntimeError("apply requires archive_dir")
        archive_path = self._archive_summary_files(removal_paths, archive_dir=archive_dir)
        summary.archive_path = str(archive_path)
        self._unlink_archived_files(removal_paths, summary)
        return summary

    def _iter_candidates(
        self,
        *,
        limit: Optional[int],
    ) -> Iterable[ArtifactLifecycleCandidate]:
        iter_candidates = getattr(self.reader, "iter_candidates")
        return iter_candidates(limit=limit, page_size=self.policy.page_size)

    def _classify_candidate(
        self,
        candidate: ArtifactLifecycleCandidate,
        summary: ArtifactLifecycleRunSummary,
        removal_paths: List[Path],
    ) -> None:
        summary.examined += 1
        try:
            result_path = result_json_path_for_candidate(candidate)
            summary_path = summary_path_for_candidate(
                candidate.storage_ref,
                candidate.metadata,
            )
            summary_exists = bool(
                summary_path and summary_path.exists() and summary_path.is_file()
            )
            if summary_exists:
                result_exists = bool(
                    result_path and result_path.exists() and result_path.is_file()
                )
                checksum_ok = checksum_matches(candidate, result_path)
            else:
                result_exists = False
                checksum_ok = True
            decision = self.policy.decide_summary_sidecar(
                candidate,
                summary_path_exists=summary_exists,
                result_json_exists=result_exists,
                checksum_matches=checksum_ok,
            )
            for reason in decision.reasons:
                summary.mark_reason(reason)
            if "missing-result-json" in decision.reasons:
                summary.missing_result += 1
            if "missing-db-pointer" in decision.reasons:
                summary.missing_db_pointer += 1
            if "active-task" in decision.reasons:
                summary.skipped_active += 1
            if decision.action == "remove_summary":
                summary.remove_summary += 1
                if summary_path is not None:
                    removal_paths.append(summary_path)
            else:
                summary.keep += 1
        except Exception as exc:
            logger.warning(
                "Artifact lifecycle candidate failed artifact_id=%s error=%s",
                candidate.artifact_id,
                exc,
            )
            summary.error += 1
            summary.mark_reason("error")

    def _archive_summary_files(self, paths: List[Path], *, archive_dir: Path) -> Path:
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"artifact-summary-sidecars-{int(time.time())}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            for path in paths:
                if path.exists() and path.is_file():
                    tar.add(path, arcname=str(path).lstrip("/"))
        return archive_path

    def _unlink_archived_files(
        self,
        paths: List[Path],
        summary: ArtifactLifecycleRunSummary,
    ) -> None:
        errors = 0
        for index, path in enumerate(paths, start=1):
            try:
                if path.exists() and path.is_file():
                    path.unlink()
                    summary.archived_summary += 1
            except OSError as exc:
                errors += 1
                summary.error += 1
                summary.mark_reason("unlink-error")
                logger.warning("Failed to remove artifact summary path=%s error=%s", path, exc)
            if index % self.policy.filesystem_batch_size == 0:
                error_ratio = errors / max(index, 1)
                if error_ratio > self.policy.max_batch_error_ratio:
                    raise RuntimeError("artifact lifecycle error ratio exceeded")
                time.sleep(self.policy.batch_sleep_seconds)


class RuntimeLifecycleApplyGate(PostgresStoreBase):
    """Runtime DB and PgBouncer gate for lifecycle apply mode."""

    def __init__(self, *, pgbouncer_admin_url: Optional[str]) -> None:
        super().__init__(db_role="core")
        self.pgbouncer_admin_url = pgbouncer_admin_url

    def assert_apply_allowed(self) -> None:
        """Raise if Postgres or PgBouncer is not safe for apply."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    "SELECT pg_is_in_recovery() AS in_recovery, "
                    "current_setting('transaction_read_only') AS read_only"
                )
            ).fetchone()
        mapping = row._mapping if hasattr(row, "_mapping") else row
        in_recovery = bool(mapping["in_recovery"])
        read_only = str(mapping["read_only"]).lower() == "on"
        if in_recovery or read_only:
            raise RuntimeError("postgres is not writable")
        if not self.pgbouncer_admin_url:
            raise RuntimeError("pgbouncer admin URL is required for apply")
        self._assert_pgbouncer_low_load()

    def _assert_pgbouncer_low_load(self) -> None:
        engine = create_engine(self.pgbouncer_admin_url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                rows = conn.execute(text("SHOW POOLS")).fetchall()
        finally:
            engine.dispose()
        for row in rows:
            values = list(row)
            if len(values) < 9:
                continue
            database_name = str(values[0])
            cl_waiting = int(values[7])
            if database_name in {"mindscape_core", "mindscape_vectors"} and cl_waiting > 0:
                raise RuntimeError("pgbouncer has waiting clients")
