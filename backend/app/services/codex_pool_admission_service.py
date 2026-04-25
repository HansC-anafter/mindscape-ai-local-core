"""
Codex pool admission service.

Provides a central gate for deciding whether the Codex pool is healthy enough
to admit a governed execution before a meeting/session spends planner turns
probing degraded runtimes live.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.app.services.codex_pool_health import coerce_datetime, read_health_metadata


_SUPPORTED_AUTH_TYPES = frozenset({"api_key", "host_session", "none"})


@dataclass(frozen=True)
class CodexPoolAdmissionDecision:
    admissible: bool
    reason: str
    preferred_runtime_id: Optional[str]
    allow_fallback: bool
    pool_enabled_runtime_count: int
    runnable_runtime_count: int
    healthy_runtime_count: int
    probation_runtime_count: int
    quarantined_runtime_count: int
    cooldown_runtime_count: int
    failure_counts: dict[str, int]
    candidate_runtime_ids: tuple[str, ...]

    def blocker_message(self) -> str:
        return (
            "Codex pool admission blocked: "
            f"{self.reason} "
            f"(runnable={self.runnable_runtime_count}, "
            f"healthy={self.healthy_runtime_count}, "
            f"probation={self.probation_runtime_count}, "
            f"quarantined={self.quarantined_runtime_count}, "
            f"cooldown={self.cooldown_runtime_count})"
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "admissible": self.admissible,
            "reason": self.reason,
            "preferred_runtime_id": self.preferred_runtime_id,
            "allow_fallback": self.allow_fallback,
            "pool_enabled_runtime_count": self.pool_enabled_runtime_count,
            "runnable_runtime_count": self.runnable_runtime_count,
            "healthy_runtime_count": self.healthy_runtime_count,
            "probation_runtime_count": self.probation_runtime_count,
            "quarantined_runtime_count": self.quarantined_runtime_count,
            "cooldown_runtime_count": self.cooldown_runtime_count,
            "failure_counts": dict(self.failure_counts),
            "candidate_runtime_ids": list(self.candidate_runtime_ids),
        }


class CodexPoolAdmissionService:
    """Evaluate whether the Codex runtime pool is healthy enough to admit execution."""

    def __init__(
        self,
        runtime_loader: Optional[Callable[[], list[Any]]] = None,
        requalification_runner: Optional[Callable[[], Any]] = None,
    ):
        self._runtime_loader = runtime_loader or self._load_pool_runtimes
        self._requalification_runner = (
            requalification_runner
            or (self._run_due_requalification if runtime_loader is None else (lambda: None))
        )

    def evaluate_execution_admission(
        self,
        *,
        preferred_runtime_id: Optional[str] = None,
        allow_fallback: bool = True,
    ) -> CodexPoolAdmissionDecision:
        try:
            self._requalification_runner()
        except Exception:
            pass
        runtimes = self._runtime_loader()
        summaries = [self._summarize_runtime(runtime) for runtime in runtimes]
        pool_enabled_runtime_count = len(summaries)
        runnable_candidates = [
            item for item in summaries if item["runnable_candidate"]
        ]
        healthy_candidates = [
            item for item in summaries if item["healthy_candidate"]
        ]
        probation_candidates = [
            item for item in summaries if item["probation_candidate"]
        ]
        quarantined_runtime_count = sum(
            1 for item in summaries if item["health_state"] == "quarantined"
        )
        cooldown_runtime_count = sum(1 for item in summaries if item["cooldown_active"])
        failure_counts = Counter(
            item["last_failure_code"]
            for item in summaries
            if item["last_failure_code"]
        )

        normalized_preferred_runtime_id = str(preferred_runtime_id or "").strip() or None
        if normalized_preferred_runtime_id:
            preferred_summary = next(
                (
                    item
                    for item in summaries
                    if item["runtime_id"] == normalized_preferred_runtime_id
                ),
                None,
            )
            if preferred_summary and preferred_summary["runnable_candidate"]:
                return CodexPoolAdmissionDecision(
                    admissible=True,
                    reason=(
                        "preferred_runtime_admitted"
                        if preferred_summary["healthy_candidate"]
                        else "preferred_runtime_runnable"
                    ),
                    preferred_runtime_id=normalized_preferred_runtime_id,
                    allow_fallback=allow_fallback,
                    pool_enabled_runtime_count=pool_enabled_runtime_count,
                    runnable_runtime_count=len(runnable_candidates),
                    healthy_runtime_count=len(healthy_candidates),
                    probation_runtime_count=len(probation_candidates),
                    quarantined_runtime_count=quarantined_runtime_count,
                    cooldown_runtime_count=cooldown_runtime_count,
                    failure_counts=dict(failure_counts),
                    candidate_runtime_ids=(normalized_preferred_runtime_id,),
                )
            if not allow_fallback:
                return CodexPoolAdmissionDecision(
                    admissible=False,
                    reason="preferred_runtime_not_runnable",
                    preferred_runtime_id=normalized_preferred_runtime_id,
                    allow_fallback=allow_fallback,
                    pool_enabled_runtime_count=pool_enabled_runtime_count,
                    runnable_runtime_count=len(runnable_candidates),
                    healthy_runtime_count=len(healthy_candidates),
                    probation_runtime_count=len(probation_candidates),
                    quarantined_runtime_count=quarantined_runtime_count,
                    cooldown_runtime_count=cooldown_runtime_count,
                    failure_counts=dict(failure_counts),
                    candidate_runtime_ids=tuple(
                        item["runtime_id"] for item in runnable_candidates
                    ),
                )

        if healthy_candidates:
            return CodexPoolAdmissionDecision(
                admissible=True,
                reason="healthy_runtime_available",
                preferred_runtime_id=normalized_preferred_runtime_id,
                allow_fallback=allow_fallback,
                pool_enabled_runtime_count=pool_enabled_runtime_count,
                runnable_runtime_count=len(runnable_candidates),
                healthy_runtime_count=len(healthy_candidates),
                probation_runtime_count=len(probation_candidates),
                quarantined_runtime_count=quarantined_runtime_count,
                cooldown_runtime_count=cooldown_runtime_count,
                failure_counts=dict(failure_counts),
                candidate_runtime_ids=tuple(
                    item["runtime_id"] for item in healthy_candidates
                ),
            )
        if runnable_candidates:
            return CodexPoolAdmissionDecision(
                admissible=True,
                reason="runnable_runtime_available",
                preferred_runtime_id=normalized_preferred_runtime_id,
                allow_fallback=allow_fallback,
                pool_enabled_runtime_count=pool_enabled_runtime_count,
                runnable_runtime_count=len(runnable_candidates),
                healthy_runtime_count=0,
                probation_runtime_count=len(probation_candidates),
                quarantined_runtime_count=quarantined_runtime_count,
                cooldown_runtime_count=cooldown_runtime_count,
                failure_counts=dict(failure_counts),
                candidate_runtime_ids=tuple(
                    item["runtime_id"] for item in runnable_candidates
                ),
            )

        return CodexPoolAdmissionDecision(
            admissible=False,
            reason="no_runnable_runtimes",
            preferred_runtime_id=normalized_preferred_runtime_id,
            allow_fallback=allow_fallback,
            pool_enabled_runtime_count=pool_enabled_runtime_count,
            runnable_runtime_count=0,
            healthy_runtime_count=0,
            probation_runtime_count=len(probation_candidates),
            quarantined_runtime_count=quarantined_runtime_count,
            cooldown_runtime_count=cooldown_runtime_count,
            failure_counts=dict(failure_counts),
            candidate_runtime_ids=(),
        )

    @staticmethod
    def _load_pool_runtimes() -> list[Any]:
        from backend.app.services.codex_pool_service import (
            CODEX_POOL_GROUP,
            CodexPoolService,
        )

        db = CodexPoolService()._get_db()
        RuntimeEnvironment = CodexPoolService()._get_model()
        try:
            return (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                    RuntimeEnvironment.pool_enabled.is_(True),
                    RuntimeEnvironment.auth_type.in_(tuple(_SUPPORTED_AUTH_TYPES)),
                )
                .all()
            )
        finally:
            db.close()

    @staticmethod
    def _run_due_requalification() -> None:
        from backend.app.services.codex_pool_requalification_service import (
            CodexPoolRequalificationService,
        )

        CodexPoolRequalificationService().sweep_due_runtimes()

    @staticmethod
    def _summarize_runtime(runtime: Any) -> dict[str, Any]:
        auth_type = str(getattr(runtime, "auth_type", "") or "")
        metadata = dict(getattr(runtime, "extra_metadata", None) or {})
        health = read_health_metadata(metadata, auth_type=auth_type)
        cooldown_until = coerce_datetime(getattr(runtime, "cooldown_until", None))
        now = datetime.now(timezone.utc)
        cooldown_active = bool(cooldown_until and cooldown_until > now)
        health_state = str(health.get("health_state") or "").strip().lower() or "healthy"
        runtime_id = str(getattr(runtime, "id", "") or "").strip()
        healthy_candidate = health_state == "healthy" and not cooldown_active
        probation_candidate = health_state == "probation" and not cooldown_active
        runnable_candidate = health_state != "quarantined" and not cooldown_active
        return {
            "runtime_id": runtime_id,
            "health_state": health_state,
            "cooldown_active": cooldown_active,
            "last_failure_code": str(health.get("last_failure_code") or "").strip().lower()
            or None,
            "runnable_candidate": runnable_candidate,
            "healthy_candidate": healthy_candidate,
            "probation_candidate": probation_candidate,
        }
