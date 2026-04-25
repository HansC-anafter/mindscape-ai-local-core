"""
Codex pool requalification service.

Provides centralized recovery for degraded pool runtimes so admission and
runtime selection do not rely on live meeting sessions to rediscover which
accounts are ready to re-enter rotation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.app.services.codex_pool_health import (
    coerce_datetime,
    read_health_metadata,
    stamp_runtime_requalified,
)


_SUPPORTED_AUTH_TYPES = frozenset({"api_key", "host_session", "none"})
_AUTH_FAILURE_CODES = frozenset({"401", "403", "deactivated_workspace", "unauthorized"})
_PROBATION_FAILURE_CODES = frozenset({"timeout", "stall"})


@dataclass(frozen=True)
class CodexPoolRequalificationSummary:
    scanned_runtime_count: int
    requalified_runtime_count: int
    cooldown_cleared_count: int
    manual_repair_required_count: int
    updated_runtime_ids: tuple[str, ...]
    manual_repair_runtime_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "scanned_runtime_count": self.scanned_runtime_count,
            "requalified_runtime_count": self.requalified_runtime_count,
            "cooldown_cleared_count": self.cooldown_cleared_count,
            "manual_repair_required_count": self.manual_repair_required_count,
            "updated_runtime_ids": list(self.updated_runtime_ids),
            "manual_repair_runtime_ids": list(self.manual_repair_runtime_ids),
        }


class CodexPoolRequalificationService:
    """Centralize due-runtime recovery for the Codex pool."""

    def __init__(
        self,
        runtime_loader: Optional[Callable[[], list[Any]]] = None,
        runtime_commit: Optional[Callable[[list[Any]], None]] = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._runtime_commit = runtime_commit

    def sweep_due_runtimes(
        self,
        *,
        now: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> CodexPoolRequalificationSummary:
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if self._runtime_loader is not None:
            runtimes = list(self._runtime_loader())
            if limit is not None and limit >= 0:
                runtimes = runtimes[:limit]
            return self._apply_requalification(
                runtimes,
                now=timestamp,
                persist_updates=self._runtime_commit,
            )

        return self._sweep_database(now=timestamp, limit=limit)

    def requalify_runtime(
        self,
        runtime_id: str,
        *,
        reason: str = "manual_override",
        now: Optional[datetime] = None,
    ) -> Optional[dict[str, Any]]:
        normalized_runtime_id = str(runtime_id or "").strip()
        if not normalized_runtime_id:
            return None

        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if self._runtime_loader is not None:
            runtimes = list(self._runtime_loader())
            runtime = next(
                (candidate for candidate in runtimes if str(getattr(candidate, "id", "") or "") == normalized_runtime_id),
                None,
            )
            if runtime is None:
                return None
            self._mark_runtime_requalified(
                runtime,
                reason=str(reason or "").strip() or "manual_override",
                now=timestamp,
            )
            if self._runtime_commit is not None:
                self._runtime_commit([runtime])
            return self._runtime_payload(runtime)

        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            runtime = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.id == normalized_runtime_id,
                    RuntimeEnvironment.pool_group == self._pool_group(),
                )
                .first()
            )
            if runtime is None:
                return None
            self._mark_runtime_requalified(
                runtime,
                reason=str(reason or "").strip() or "manual_override",
                now=timestamp,
            )
            db.commit()
            db.refresh(runtime)
            return self._runtime_payload(runtime)
        finally:
            db.close()

    def _sweep_database(
        self,
        *,
        now: datetime,
        limit: Optional[int],
    ) -> CodexPoolRequalificationSummary:
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            query = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.pool_group == self._pool_group(),
                    RuntimeEnvironment.pool_enabled.is_(True),
                    RuntimeEnvironment.auth_type.in_(tuple(_SUPPORTED_AUTH_TYPES)),
                )
                .order_by(RuntimeEnvironment.updated_at.asc().nullsfirst())
            )
            if limit is not None and limit >= 0:
                query = query.limit(limit)
            runtimes = list(query.all())

            def _commit(updated_runtimes: list[Any]) -> None:
                if updated_runtimes:
                    db.commit()

            summary = self._apply_requalification(
                runtimes,
                now=now,
                persist_updates=_commit,
            )
            if not summary.updated_runtime_ids:
                db.rollback()
            return summary
        finally:
            db.close()

    def _apply_requalification(
        self,
        runtimes: list[Any],
        *,
        now: datetime,
        persist_updates: Optional[Callable[[list[Any]], None]],
    ) -> CodexPoolRequalificationSummary:
        updated_runtimes: list[Any] = []
        updated_runtime_ids: list[str] = []
        manual_repair_runtime_ids: list[str] = []
        requalified_count = 0
        cooldown_cleared_count = 0

        for runtime in runtimes:
            action = self._due_action(runtime, now=now)
            runtime_id = str(getattr(runtime, "id", "") or "").strip()
            if action == "probation_requalified":
                self._mark_runtime_requalified(
                    runtime,
                    reason="probation_timeout_cooldown_expired",
                    now=now,
                )
                updated_runtimes.append(runtime)
                updated_runtime_ids.append(runtime_id)
                requalified_count += 1
            elif action == "seed_probation_promoted":
                self._mark_runtime_requalified(
                    runtime,
                    reason="seed_probation_promoted",
                    now=now,
                )
                updated_runtimes.append(runtime)
                updated_runtime_ids.append(runtime_id)
                requalified_count += 1
            elif action == "stale_auth_scope_requalified":
                self._mark_runtime_requalified(
                    runtime,
                    reason="stale_auth_scope_replaced",
                    now=now,
                )
                updated_runtimes.append(runtime)
                updated_runtime_ids.append(runtime_id)
                requalified_count += 1
            elif action == "cooldown_cleared":
                self._mark_runtime_requalified(
                    runtime,
                    reason="quota_cooldown_expired",
                    now=now,
                )
                updated_runtimes.append(runtime)
                updated_runtime_ids.append(runtime_id)
                cooldown_cleared_count += 1
            elif action == "manual_repair_required":
                manual_repair_runtime_ids.append(runtime_id)

        if updated_runtimes and persist_updates is not None:
            persist_updates(updated_runtimes)

        return CodexPoolRequalificationSummary(
            scanned_runtime_count=len(runtimes),
            requalified_runtime_count=requalified_count,
            cooldown_cleared_count=cooldown_cleared_count,
            manual_repair_required_count=len(manual_repair_runtime_ids),
            updated_runtime_ids=tuple(updated_runtime_ids),
            manual_repair_runtime_ids=tuple(manual_repair_runtime_ids),
        )

    @staticmethod
    def _due_action(runtime: Any, *, now: datetime) -> Optional[str]:
        metadata = dict(getattr(runtime, "extra_metadata", None) or {})
        auth_type = str(getattr(runtime, "auth_type", "") or "")
        health = read_health_metadata(metadata, auth_type=auth_type)
        health_state = str(health.get("health_state") or "").strip().lower() or "healthy"
        failure_code = str(
            health.get("last_failure_code") or getattr(runtime, "last_error_code", "") or ""
        ).strip().lower() or None
        cooldown_until = coerce_datetime(getattr(runtime, "cooldown_until", None))
        cooldown_expired = bool(cooldown_until and cooldown_until <= now)
        cooldown_active = bool(cooldown_until and cooldown_until > now)

        if (
            health_state == "quarantined"
            and failure_code in _AUTH_FAILURE_CODES
            and CodexPoolRequalificationService._is_stale_auth_failure_scope(
                metadata,
                health=health,
            )
        ):
            return "stale_auth_scope_requalified"
        if health_state == "quarantined" and failure_code in _AUTH_FAILURE_CODES and cooldown_expired:
            return "manual_repair_required"
        if health_state == "probation" and not failure_code and not cooldown_active:
            return "seed_probation_promoted"
        if health_state == "probation" and failure_code in _PROBATION_FAILURE_CODES and cooldown_expired:
            return "probation_requalified"
        if health_state in {"healthy", "probation"} and failure_code == "429" and cooldown_expired:
            return "cooldown_cleared"
        return None

    @staticmethod
    def _is_stale_auth_failure_scope(
        metadata: dict[str, Any],
        *,
        health: dict[str, Any],
    ) -> bool:
        failure_scope_key = str(health.get("failure_scope_key") or "").strip()
        if not failure_scope_key:
            return False

        if failure_scope_key.startswith("account:"):
            account_key = str(metadata.get("account_key") or "").strip()
            return bool(account_key and failure_scope_key != f"account:{account_key}")

        if failure_scope_key.startswith("seed:"):
            seed_home = str(
                metadata.get("managed_seed_source_home")
                or metadata.get("quota_scope_home")
                or ""
            ).strip()
            return bool(seed_home and failure_scope_key != f"seed:{seed_home}")

        return False

    @staticmethod
    def _mark_runtime_requalified(
        runtime: Any,
        *,
        reason: str,
        now: datetime,
    ) -> None:
        auth_type = str(getattr(runtime, "auth_type", "") or "")
        runtime.cooldown_until = None
        runtime.last_error_code = None
        runtime.extra_metadata = stamp_runtime_requalified(
            dict(getattr(runtime, "extra_metadata", None) or {}),
            reason=reason,
            auth_type=auth_type,
            now=now,
        )

    @staticmethod
    def _runtime_payload(runtime: Any) -> dict[str, Any]:
        health = read_health_metadata(
            dict(getattr(runtime, "extra_metadata", None) or {}),
            auth_type=str(getattr(runtime, "auth_type", "") or ""),
        )
        return {
            "id": str(getattr(runtime, "id", "") or "").strip(),
            "cooldown_until": (
                getattr(runtime, "cooldown_until", None).isoformat()
                if getattr(runtime, "cooldown_until", None)
                else None
            ),
            "last_error_code": getattr(runtime, "last_error_code", None),
            "runtime_health_state": health.get("health_state"),
            "last_requalified_at": health.get("last_requalified_at"),
            "last_requalification_reason": health.get("last_requalification_reason"),
        }

    @staticmethod
    def _pool_group() -> str:
        from backend.app.services.codex_pool_service import CODEX_POOL_GROUP

        return CODEX_POOL_GROUP

    @staticmethod
    def _get_db():
        from backend.app.services.codex_pool_service import CodexPoolService

        return CodexPoolService()._get_db()

    @staticmethod
    def _get_model():
        from backend.app.services.codex_pool_service import CodexPoolService

        return CodexPoolService()._get_model()
