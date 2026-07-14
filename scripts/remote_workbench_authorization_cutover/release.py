"""Facade for the single Phase06 backup, DB, package, and restore path."""

from __future__ import annotations

import csv
import io
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from .backup import BackupGate
from .http import HttpClient
from .install_receipt import (
    require_terminal_install_attempt,
    verify_known_good_restore_job,
)
from .install_attempt_state import ACTIVE_INSTALL_STATES
from .io import CommandExecutor, CutoverError
from .pack_release import PackReleaseGate
from .pgbouncer_admin import pgbouncer_admin_csv_command
from .pgbouncer_capacity import PgBouncerCapacityGate
from .query_plan import QueryPlanGate


class ReleaseGate:
    """Expose one workflow-facing release path backed by modular hard gates."""

    def __init__(
        self,
        *,
        repo_root: Path,
        cloud_worktree: Path,
        executor: CommandExecutor,
        http: HttpClient,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.repo_root = repo_root
        self.cloud_worktree = cloud_worktree
        self.executor = executor
        self.http = http
        self.backup = BackupGate(repo_root=repo_root, executor=executor)
        self.pgbouncer_capacity = PgBouncerCapacityGate(
            repo_root=repo_root,
            executor=executor,
        )
        self.query_plan = QueryPlanGate(executor)
        self.pack = PackReleaseGate(
            cloud_worktree=cloud_worktree,
            executor=executor,
            http=http,
            sleep=sleep,
            monotonic=monotonic,
        )

    def require_no_active_install_jobs(self) -> None:
        """Require the durable install queue to be idle before mutation."""

        states = ",".join(f"'{state}'" for state in ACTIVE_INSTALL_STATES)
        query = f"SELECT count(*) FROM capability_install_jobs WHERE state IN ({states});"
        raw = self.executor.run(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-postgres",
                "psql",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-tAc",
                query,
            ],
            timeout_seconds=20.0,
        ).strip()
        if raw != "0":
            raise CutoverError("A capability install job is still active")

    def verify_database_pools(
        self,
        secure_dir: Path | None = None,
        evidence_label: str | None = None,
    ) -> None:
        """Require writable PostgreSQL and idle PgBouncer wait queues."""

        if (secure_dir is None) != (evidence_label is None):
            raise CutoverError("PgBouncer capacity evidence requires directory and label")

        database = self.executor.run(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-postgres",
                "psql",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-tAc",
                "SELECT pg_is_in_recovery()::text || '|' || "
                "current_setting('transaction_read_only') || '|' || "
                "current_setting('default_transaction_read_only');",
            ],
            timeout_seconds=20.0,
        ).strip()
        if database not in {"false|off|off", "f|off|off"}:
            raise CutoverError("PostgreSQL is not writable")
        pools = self.executor.run(
            pgbouncer_admin_csv_command("SHOW POOLS;"),
            timeout_seconds=20.0,
        )
        rows = list(csv.DictReader(io.StringIO(pools)))
        if not rows:
            raise CutoverError("PgBouncer returned no pool evidence")
        core_rows = [row for row in rows if row.get("database") == "mindscape_core"]
        if not core_rows:
            raise CutoverError("PgBouncer mindscape_core pool is missing")
        for row in rows:
            if int(row.get("cl_waiting") or 0) != 0 or int(row.get("maxwait") or 0) != 0:
                raise CutoverError("PgBouncer has waiting clients")
        core_connections = sum(
            int(row.get("sv_active") or 0) + int(row.get("sv_idle") or 0)
            for row in core_rows
        )
        if core_connections > 40:
            raise CutoverError("PgBouncer server connection budget exceeds 40")
        if secure_dir is not None and evidence_label is not None:
            self.pgbouncer_capacity.verify_and_persist(secure_dir, evidence_label)

    def verify_workspace_rows(self, target: str, inheritance: str) -> None:
        """Prove both workspace rows exist and inheritance has no direct policy row."""

        sql = f"""
SELECT json_build_object(
  'workspace_ids', COALESCE((
    SELECT json_agg(id::text ORDER BY id::text)
    FROM workspaces
    WHERE id::text IN ('{target}', '{inheritance}')
  ), '[]'::json),
  'inheritance_policy_rows', (
    SELECT count(*)
    FROM workspace_mobile_workbench_gateway_policies
    WHERE workspace_id::text = '{inheritance}'
  )
)::text;
""".strip()
        raw = self.executor.run(
            [
                "docker", "exec", "mindscape-ai-local-core-postgres",
                "psql", "-XqAt", "-U", "mindscape", "-d", "mindscape_core",
                "-v", "ON_ERROR_STOP=1", "-c", sql,
            ],
            timeout_seconds=20.0,
        ).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise CutoverError("Workspace existence DB evidence is malformed") from error
        if payload != {
            "workspace_ids": sorted([target, inheritance]),
            "inheritance_policy_rows": 0,
        }:
            raise CutoverError("Workspace rows or inheritance default-deny state are missing")

    def verify_or_create_backup(self) -> Path:
        return self.backup.verify_or_create()

    def verify_effective_policy_query_plan(self, workspace_id: str) -> None:
        self.query_plan.verify(workspace_id)

    def capture_known_good(self, secure_dir: Path) -> dict[str, Any]:
        return self.pack.capture_known_good(secure_dir)

    def package_current(self) -> Path:
        return self.pack.package_current()

    def install_current(self, archive: Path, secure_dir: Path) -> dict[str, Any]:
        return self.pack.install_current(
            archive,
            secure_dir,
            before_create=self._verify_install_create_gates,
        )

    def _verify_install_create_gates(self) -> None:
        """Close the DB and queue race immediately before a new intake POST."""

        self.require_no_active_install_jobs()
        self.verify_database_pools()

    def require_install_attempt_terminal(self, secure_dir: Path) -> dict[str, Any]:
        return require_terminal_install_attempt(self.http, secure_dir)

    def require_restore_attempt_terminal(self, secure_dir: Path) -> dict[str, Any]:
        return require_terminal_install_attempt(
            self.http,
            secure_dir,
            attempt_kind="restore",
        )

    def verify_restore_job(self, secure_dir: Path, job: dict[str, Any]) -> None:
        verify_known_good_restore_job(secure_dir, job)
        self.pack.verify_installed_runtime(job)

    def restore_known_good(self, secure_dir: Path) -> dict[str, Any]:
        return self.pack.restore_known_good(
            secure_dir,
            before_create=self._verify_install_create_gates,
        )

    def verify_installed_runtime(self, job: dict[str, Any]) -> None:
        self.pack.verify_installed_runtime(job)

    def source_identity(self) -> dict[str, str]:
        """Read the exact already repository-locked Local and Cloud commits."""

        pattern = re.compile(r"^[a-f0-9]{40}$")
        result = {
            "local_commit": self.executor.run(
                ["git", "-C", str(self.repo_root), "rev-parse", "HEAD"],
                timeout_seconds=20.0,
            ).strip(),
            "cloud_commit": self.executor.run(
                ["git", "-C", str(self.cloud_worktree), "rev-parse", "HEAD"],
                timeout_seconds=20.0,
            ).strip(),
        }
        if any(not pattern.fullmatch(value) for value in result.values()):
            raise CutoverError("Repository source commit identity is malformed")
        return result
