"""
Codex CLI runtime pool service.

Supports rotating across multiple Codex runtimes backed by either:
- API keys
- Host sessions isolated via runtime metadata (for example CODEX_HOME)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import or_
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

CODEX_POOL_GROUP = "codex-cli-pool"
BASE_COOLDOWN_SECONDS = 300
MAX_COOLDOWN_SECONDS = 1800
BACKOFF_MULTIPLIER = 3
_HOST_SESSION_ENV_KEYS = (
    "CODEX_HOME",
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
)


class CodexPoolService:
    """Select and cool down Codex runtimes from the shared pool."""

    def _get_db(self):
        try:
            from backend.app.database.session import get_db_postgres as get_db
        except ImportError:
            try:
                from backend.app.database import get_db_postgres as get_db
            except ImportError:
                from mindscape.di.providers import get_db_session as get_db
        return next(get_db())

    def _get_model(self):
        from backend.app.models.runtime_environment import RuntimeEnvironment

        return RuntimeEnvironment

    def get_active_auth_bundle(
        self,
        *,
        preferred_runtime_id: Optional[str] = None,
        allow_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Return env/auth metadata for the best available Codex runtime."""
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            from backend.app.services.runtime_auth_service import RuntimeAuthService

            now = datetime.now(timezone.utc)
            runtimes = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                    RuntimeEnvironment.pool_enabled.is_(True),
                    RuntimeEnvironment.auth_type.in_(("api_key", "host_session", "none")),
                    or_(
                        RuntimeEnvironment.cooldown_until.is_(None),
                        RuntimeEnvironment.cooldown_until < now,
                    ),
                )
                .order_by(
                    RuntimeEnvironment.pool_priority.asc(),
                    RuntimeEnvironment.last_used_at.asc().nullsfirst(),
                )
                .all()
            )

            if preferred_runtime_id:
                preferred = next(
                    (runtime for runtime in runtimes if runtime.id == preferred_runtime_id),
                    None,
                )
                if not preferred and not allow_fallback:
                    return {
                        "error": f"Preferred Codex runtime unavailable: {preferred_runtime_id}",
                    }
                if preferred:
                    runtimes = [
                        preferred,
                        *[runtime for runtime in runtimes if runtime.id != preferred_runtime_id],
                    ]
                elif allow_fallback:
                    logger.warning(
                        "Preferred Codex runtime %s unavailable, falling back to pool ordering",
                        preferred_runtime_id,
                    )

            auth_service = RuntimeAuthService()
            available_runtime_count = len(runtimes)
            available_quota_scope_count = self._count_distinct_quota_scopes(runtimes)
            for runtime in runtimes:
                bundle = self._build_runtime_bundle(runtime, auth_service)
                if not bundle:
                    continue
                runtime.last_used_at = func.now()
                runtime.last_error_code = None
                db.commit()
                bundle["selected_runtime_id"] = runtime.id
                bundle["available_runtime_count"] = available_runtime_count
                bundle["available_quota_scope_count"] = available_quota_scope_count
                return bundle

            if preferred_runtime_id and not allow_fallback:
                return {
                    "error": f"Preferred Codex runtime unavailable: {preferred_runtime_id}",
                    "available_runtime_count": available_runtime_count,
                    "available_quota_scope_count": available_quota_scope_count,
                }
            return {
                "error": "No available Codex runtimes in pool",
                "available_runtime_count": available_runtime_count,
                "available_quota_scope_count": available_quota_scope_count,
            }
        finally:
            db.close()

    def report_quota_exhausted(self, runtime_id: str) -> Optional[Dict[str, Any]]:
        """Mark a runtime as temporarily cooled down after quota exhaustion."""
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            runtime = (
                db.query(RuntimeEnvironment)
                .filter(
                    RuntimeEnvironment.id == runtime_id,
                    RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                )
                .first()
            )
            if not runtime:
                return None

            now = datetime.now(timezone.utc)
            consecutive = self._count_recent_quota_errors(runtime)
            cooldown_secs = min(
                BASE_COOLDOWN_SECONDS * (BACKOFF_MULTIPLIER**consecutive),
                MAX_COOLDOWN_SECONDS,
            )
            cooldown_until = now + timedelta(seconds=cooldown_secs)
            quota_scope_key = self._quota_scope_key(runtime)
            affected_runtimes = [runtime]
            if quota_scope_key:
                sibling_runtimes = (
                    db.query(RuntimeEnvironment)
                    .filter(
                        RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                        RuntimeEnvironment.user_id == runtime.user_id,
                    )
                    .all()
                )
                affected_runtimes = [
                    candidate
                    for candidate in sibling_runtimes
                    if self._quota_scope_key(candidate) == quota_scope_key
                ] or [runtime]

            for candidate in affected_runtimes:
                candidate.cooldown_until = cooldown_until
                candidate.last_error_code = "429"
            db.commit()
            db.refresh(runtime)
            logger.info(
                "Codex runtime %s quota exhausted, cooldown %ss (consecutive=%s affected=%s scope=%s)",
                runtime_id,
                cooldown_secs,
                consecutive + 1,
                len(affected_runtimes),
                quota_scope_key or "runtime_only",
            )
            return runtime.to_dict(include_sensitive=False)
        finally:
            db.close()

    @classmethod
    def _build_runtime_bundle(
        cls,
        runtime: Any,
        auth_service: Any,
    ) -> Optional[Dict[str, Any]]:
        auth_type = str(getattr(runtime, "auth_type", "") or "none").strip().lower()
        if auth_type == "api_key":
            try:
                decrypted = auth_service.decrypt_credentials(runtime.auth_config or {})
            except Exception:
                logger.exception("Failed to decrypt Codex API key for runtime %s", runtime.id)
                return None
            api_key = str(decrypted.get("api_key") or "").strip()
            if not api_key:
                return None
            return {
                "auth_mode": "openai_api_key",
                "env": {"OPENAI_API_KEY": api_key},
                "runtime_auth_type": auth_type,
            }

        if auth_type in {"host_session", "none"}:
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            env = cls._host_session_env_from_metadata(metadata)
            return {
                "auth_mode": "host_session",
                "env": env,
                "runtime_auth_type": "host_session",
            }

        return None

    @classmethod
    def _host_session_env_from_metadata(cls, metadata: Dict[str, Any]) -> Dict[str, str]:
        env: Dict[str, str] = {}
        codex_home = (
            metadata.get("codex_home")
            or metadata.get("host_session_home")
            or metadata.get("CODEX_HOME")
        )
        if isinstance(codex_home, str) and codex_home.strip():
            env["CODEX_HOME"] = codex_home.strip()

        for key in _HOST_SESSION_ENV_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                env[key] = value.strip()

        nested_env = metadata.get("env")
        if isinstance(nested_env, dict):
            for key in _HOST_SESSION_ENV_KEYS:
                value = nested_env.get(key)
                if isinstance(value, str) and value.strip():
                    env[key] = value.strip()
        return env

    @staticmethod
    def _count_recent_quota_errors(runtime: Any) -> int:
        if getattr(runtime, "last_error_code", None) != "429":
            return 0
        cooldown_until = getattr(runtime, "cooldown_until", None)
        if not cooldown_until:
            return 0
        now = datetime.now(timezone.utc)
        if cooldown_until <= now:
            return 0

        remaining = (cooldown_until - now).total_seconds()
        if remaining <= BASE_COOLDOWN_SECONDS:
            return 0
        if remaining <= BASE_COOLDOWN_SECONDS * BACKOFF_MULTIPLIER:
            return 1
        return 2

    @staticmethod
    def _quota_scope_key(runtime: Any) -> Optional[str]:
        metadata = dict(getattr(runtime, "extra_metadata", None) or {})
        value = str(metadata.get("quota_scope_key") or "").strip()
        return value or None

    @classmethod
    def _count_distinct_quota_scopes(cls, runtimes: list[Any]) -> int:
        scopes = {
            cls._quota_scope_key(runtime) or f"runtime:{getattr(runtime, 'id', '')}"
            for runtime in runtimes
        }
        return len(scopes)
