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

from backend.app.services.codex_pool_health import (
    coerce_datetime,
    is_executable_runtime_metadata,
    read_health_metadata,
    runtime_probe_available,
)


_SUPPORTED_AUTH_TYPES = frozenset({"api_key", "host_session", "none"})


@dataclass(frozen=True)
class CodexPoolAdmissionDecision:
    admissible: bool
    reason: str
    preferred_runtime_id: Optional[str]
    allow_runtime_substitution: bool
    pool_enabled_runtime_count: int
    runnable_runtime_count: int
    healthy_runtime_count: int
    probation_runtime_count: int
    quarantined_runtime_count: int
    cooldown_runtime_count: int
    account_home_candidate_count: int
    probe_available_runtime_count: int
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
            "allow_runtime_substitution": self.allow_runtime_substitution,
            "pool_enabled_runtime_count": self.pool_enabled_runtime_count,
            "runnable_runtime_count": self.runnable_runtime_count,
            "healthy_runtime_count": self.healthy_runtime_count,
            "probation_runtime_count": self.probation_runtime_count,
            "quarantined_runtime_count": self.quarantined_runtime_count,
            "cooldown_runtime_count": self.cooldown_runtime_count,
            "account_home_candidate_count": self.account_home_candidate_count,
            "probe_available_runtime_count": self.probe_available_runtime_count,
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
        allow_runtime_substitution: bool = False,
        require_probe_available: bool = False,
    ) -> CodexPoolAdmissionDecision:
        try:
            self._requalification_runner()
        except Exception:
            pass
        runtimes = self._runtime_loader()
        summaries = [
            self._summarize_runtime(
                runtime,
                require_probe_available=require_probe_available,
            )
            for runtime in runtimes
        ]
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
        account_home_candidate_count = sum(
            1 for item in summaries if item["account_home_candidate"]
        )
        probe_available_runtime_count = sum(
            1 for item in summaries if item["probe_available"]
        )
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
                    allow_runtime_substitution=allow_runtime_substitution,
                    pool_enabled_runtime_count=pool_enabled_runtime_count,
                    runnable_runtime_count=len(runnable_candidates),
                    healthy_runtime_count=len(healthy_candidates),
                    probation_runtime_count=len(probation_candidates),
                    quarantined_runtime_count=quarantined_runtime_count,
                    cooldown_runtime_count=cooldown_runtime_count,
                    account_home_candidate_count=account_home_candidate_count,
                    probe_available_runtime_count=probe_available_runtime_count,
                    failure_counts=dict(failure_counts),
                    candidate_runtime_ids=(normalized_preferred_runtime_id,),
                )
            if not allow_runtime_substitution:
                return CodexPoolAdmissionDecision(
                    admissible=False,
                    reason="preferred_runtime_not_runnable",
                    preferred_runtime_id=normalized_preferred_runtime_id,
                    allow_runtime_substitution=allow_runtime_substitution,
                    pool_enabled_runtime_count=pool_enabled_runtime_count,
                    runnable_runtime_count=len(runnable_candidates),
                    healthy_runtime_count=len(healthy_candidates),
                    probation_runtime_count=len(probation_candidates),
                    quarantined_runtime_count=quarantined_runtime_count,
                    cooldown_runtime_count=cooldown_runtime_count,
                    account_home_candidate_count=account_home_candidate_count,
                    probe_available_runtime_count=probe_available_runtime_count,
                    failure_counts=dict(failure_counts),
                    candidate_runtime_ids=tuple(
                        item["runtime_id"] for item in runnable_candidates
                    ),
                )

        if require_probe_available and account_home_candidate_count <= 0:
            return CodexPoolAdmissionDecision(
                admissible=False,
                reason="no_account_home_candidates",
                preferred_runtime_id=normalized_preferred_runtime_id,
                allow_runtime_substitution=allow_runtime_substitution,
                pool_enabled_runtime_count=pool_enabled_runtime_count,
                runnable_runtime_count=len(runnable_candidates),
                healthy_runtime_count=len(healthy_candidates),
                probation_runtime_count=len(probation_candidates),
                quarantined_runtime_count=quarantined_runtime_count,
                cooldown_runtime_count=cooldown_runtime_count,
                account_home_candidate_count=account_home_candidate_count,
                probe_available_runtime_count=probe_available_runtime_count,
                failure_counts=dict(failure_counts),
                candidate_runtime_ids=(),
            )

        if healthy_candidates:
            return CodexPoolAdmissionDecision(
                admissible=True,
                reason="healthy_runtime_available",
                preferred_runtime_id=normalized_preferred_runtime_id,
                allow_runtime_substitution=allow_runtime_substitution,
                pool_enabled_runtime_count=pool_enabled_runtime_count,
                runnable_runtime_count=len(runnable_candidates),
                healthy_runtime_count=len(healthy_candidates),
                probation_runtime_count=len(probation_candidates),
                quarantined_runtime_count=quarantined_runtime_count,
                cooldown_runtime_count=cooldown_runtime_count,
                account_home_candidate_count=account_home_candidate_count,
                probe_available_runtime_count=probe_available_runtime_count,
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
                allow_runtime_substitution=allow_runtime_substitution,
                pool_enabled_runtime_count=pool_enabled_runtime_count,
                runnable_runtime_count=len(runnable_candidates),
                healthy_runtime_count=0,
                probation_runtime_count=len(probation_candidates),
                quarantined_runtime_count=quarantined_runtime_count,
                cooldown_runtime_count=cooldown_runtime_count,
                account_home_candidate_count=account_home_candidate_count,
                probe_available_runtime_count=probe_available_runtime_count,
                failure_counts=dict(failure_counts),
                candidate_runtime_ids=tuple(
                    item["runtime_id"] for item in runnable_candidates
                ),
            )

        blocked_reason = (
            "no_probe_available_runtimes"
            if require_probe_available and account_home_candidate_count > 0
            else "no_runnable_runtimes"
        )
        return CodexPoolAdmissionDecision(
            admissible=False,
            reason=blocked_reason,
            preferred_runtime_id=normalized_preferred_runtime_id,
            allow_runtime_substitution=allow_runtime_substitution,
            pool_enabled_runtime_count=pool_enabled_runtime_count,
            runnable_runtime_count=0,
            healthy_runtime_count=0,
            probation_runtime_count=len(probation_candidates),
            quarantined_runtime_count=quarantined_runtime_count,
            cooldown_runtime_count=cooldown_runtime_count,
            account_home_candidate_count=account_home_candidate_count,
            probe_available_runtime_count=probe_available_runtime_count,
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
    def _summarize_runtime(
        runtime: Any,
        *,
        require_probe_available: bool = False,
    ) -> dict[str, Any]:
        auth_type = str(getattr(runtime, "auth_type", "") or "")
        metadata = dict(getattr(runtime, "extra_metadata", None) or {})
        health = read_health_metadata(metadata, auth_type=auth_type)
        cooldown_until = coerce_datetime(getattr(runtime, "cooldown_until", None))
        now = datetime.now(timezone.utc)
        cooldown_active = bool(cooldown_until and cooldown_until > now)
        health_state = str(health.get("health_state") or "").strip().lower() or "healthy"
        executable_seed = is_executable_runtime_metadata(metadata, auth_type=auth_type)
        seed_kind = str(health.get("seed_kind") or "").strip().lower()
        runtime_id = str(getattr(runtime, "id", "") or "").strip()
        probe_available = runtime_probe_available(metadata)
        probe_gate_passed = (not require_probe_available) or probe_available
        account_home_candidate = executable_seed and seed_kind == "account_home"
        healthy_candidate = (
            executable_seed
            and health_state == "healthy"
            and not cooldown_active
            and probe_gate_passed
        )
        probation_candidate = (
            executable_seed
            and health_state == "probation"
            and not cooldown_active
            and probe_gate_passed
        )
        runnable_candidate = (
            executable_seed
            and health_state != "quarantined"
            and not cooldown_active
            and probe_gate_passed
        )
        return {
            "runtime_id": runtime_id,
            "health_state": health_state,
            "seed_kind": seed_kind,
            "cooldown_active": cooldown_active,
            "last_failure_code": str(health.get("last_failure_code") or "").strip().lower()
            or None,
            "account_home_candidate": account_home_candidate,
            "probe_available": probe_available,
            "runnable_candidate": runnable_candidate,
            "healthy_candidate": healthy_candidate,
            "probation_candidate": probation_candidate,
        }
