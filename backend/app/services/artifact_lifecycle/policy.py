"""Retention decisions for generated artifact sidecars."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional, Tuple


LifecycleAction = Literal["keep", "remove_summary", "skip"]

TERMINAL_TASK_STATUSES = frozenset(
    {
        "succeeded",
        "success",
        "completed",
        "complete",
        "failed",
        "error",
        "cancelled",
        "canceled",
        "cancelled_by_user",
        "expired",
    }
)

ACTIVE_TASK_STATUSES = frozenset(
    {
        "pending",
        "queued",
        "claimed",
        "running",
        "in_progress",
        "resuming",
        "retrying",
        "waiting",
        "waiting_to_resume",
        "waiting_for_resources",
        "waiting_db",
    }
)


@dataclass(frozen=True)
class ArtifactLifecycleCandidate:
    """Bounded DB projection for one artifact result object."""

    artifact_id: str
    workspace_id: str
    task_id: Optional[str] = None
    execution_id: Optional[str] = None
    storage_ref: Optional[str] = None
    result_json_path: Optional[str] = None
    checksum_sha256: Optional[str] = None
    bytes_count: Optional[int] = None
    summary: Optional[str] = None
    manifest_summary: Optional[str] = None
    task_status: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def summary_text(self) -> str:
        """Return the best bounded summary available from DB state."""
        for value in (self.manifest_summary, self.summary):
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""


@dataclass(frozen=True)
class ArtifactLifecycleDecision:
    """Policy result for a generated artifact sidecar."""

    action: LifecycleAction
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class ArtifactLifecyclePolicy:
    """Shared artifact lifecycle limits and eligibility rules."""

    page_size: int = 200
    filesystem_batch_size: int = 100
    batch_sleep_seconds: float = 0.25
    max_batch_error_ratio: float = 0.01
    require_result_json_for_summary_removal: bool = True

    def decide_summary_sidecar(
        self,
        candidate: ArtifactLifecycleCandidate,
        *,
        summary_path_exists: bool,
        result_json_exists: bool,
        checksum_matches: bool = True,
        consumer_requires_summary_file: bool = False,
    ) -> ArtifactLifecycleDecision:
        """Decide whether a physical summary sidecar can be removed."""
        if is_active_status(candidate.task_status):
            return ArtifactLifecycleDecision("skip", ("active-task",))
        if not candidate.storage_ref and not candidate.result_json_path:
            return ArtifactLifecycleDecision("skip", ("missing-db-pointer",))
        if not candidate.summary_text:
            return ArtifactLifecycleDecision("skip", ("missing-db-summary",))
        if not summary_path_exists:
            return ArtifactLifecycleDecision("keep", ("summary-missing",))
        if self.require_result_json_for_summary_removal and not result_json_exists:
            return ArtifactLifecycleDecision("skip", ("missing-result-json",))
        if not checksum_matches:
            return ArtifactLifecycleDecision("skip", ("checksum-mismatch",))
        if consumer_requires_summary_file:
            return ArtifactLifecycleDecision("skip", ("consumer-contract",))
        return ArtifactLifecycleDecision("remove_summary", ("derived-sidecar",))


def is_active_status(status: Optional[str]) -> bool:
    """Return True when task status should block filesystem compaction."""
    if not isinstance(status, str) or not status.strip():
        return False
    normalized = status.strip().lower()
    if normalized in TERMINAL_TASK_STATUSES:
        return False
    return normalized in ACTIVE_TASK_STATUSES
