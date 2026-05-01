"""
Codex CLI runtime pool service.

Supports rotating across multiple Codex runtimes backed by either:
- API keys
- Host sessions isolated via runtime metadata (for example CODEX_HOME)
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy import or_, text
from sqlalchemy.sql import func

from .codex_pool_health import (
    auth_failure_scope_key,
    coerce_datetime,
    health_state_rank,
    read_health_metadata,
    seed_kind_rank,
    stamp_runtime_failure,
    stamp_runtime_selected,
    stamp_runtime_success,
)

logger = logging.getLogger(__name__)

CODEX_POOL_GROUP = "codex-cli-pool"
BASE_COOLDOWN_SECONDS = 300
MAX_COOLDOWN_SECONDS = 1800
BACKOFF_MULTIPLIER = 3
AUTH_FAILURE_COOLDOWN_SECONDS = 1800
_HOST_SESSION_ENV_KEYS = (
    "CODEX_HOME",
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
)


class CodexPoolService:
    """Select and cool down Codex runtimes from the shared pool."""

    def __init__(self, requalification_runner: Optional[Callable[[], Any]] = None) -> None:
        self._requalification_runner = (
            requalification_runner or self._run_due_requalification
        )

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
        allow_runtime_substitution: Optional[bool] = None,
        allow_fallback: Optional[bool] = None,
        excluded_runtime_ids: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        """Return env/auth metadata for the best available Codex runtime."""
        if allow_runtime_substitution is None:
            allow_runtime_substitution = True if allow_fallback is None else bool(allow_fallback)
        else:
            allow_runtime_substitution = bool(allow_runtime_substitution)
        excluded_runtime_ids = {
            str(runtime_id).strip()
            for runtime_id in (excluded_runtime_ids or set())
            if str(runtime_id).strip()
        }
        try:
            self._requalification_runner()
        except Exception:
            logger.warning("Codex pool requalification sweep failed before selection", exc_info=True)
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
            from backend.app.services.runtime_auth_service import RuntimeAuthService

            try:
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
                    .all()
                )
                if excluded_runtime_ids:
                    runtimes = [
                        runtime
                        for runtime in runtimes
                        if str(getattr(runtime, "id", "") or "") not in excluded_runtime_ids
                    ]
                runtimes = self._sort_candidate_runtimes(runtimes)

                if not preferred_runtime_id and not allow_runtime_substitution:
                    return {
                        "error": "No preferred Codex runtime configured; runtime substitution is disabled.",
                        "available_runtime_count": len(runtimes),
                        "available_quota_scope_count": self._count_distinct_quota_scopes(runtimes),
                    }

                if preferred_runtime_id:
                    preferred = next(
                        (runtime for runtime in runtimes if runtime.id == preferred_runtime_id),
                        None,
                    )
                    if not preferred and not allow_runtime_substitution:
                        return {
                            "error": f"Preferred Codex runtime unavailable: {preferred_runtime_id}",
                        }
                    if preferred:
                        runtimes = [
                            preferred,
                            *[
                                runtime for runtime in runtimes if runtime.id != preferred_runtime_id
                            ],
                        ]
                    elif allow_runtime_substitution:
                        logger.warning(
                            "Preferred Codex runtime %s unavailable, using ordered pool candidates",
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
                    runtime.extra_metadata = stamp_runtime_selected(
                        dict(getattr(runtime, "extra_metadata", None) or {}),
                        auth_type=str(getattr(runtime, "auth_type", "") or ""),
                    )
                    db.commit()
                    bundle["selected_runtime_id"] = runtime.id
                    bundle["available_runtime_count"] = available_runtime_count
                    bundle["available_quota_scope_count"] = available_quota_scope_count
                    bundle.update(
                        self._bundle_health_payload(
                            runtime.extra_metadata,
                            auth_type=str(getattr(runtime, "auth_type", "") or ""),
                        )
                    )
                    return bundle

                if preferred_runtime_id and not allow_runtime_substitution:
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
            except Exception:
                if not hasattr(db, "execute"):
                    raise
                if hasattr(db, "rollback"):
                    db.rollback()
                logger.warning(
                    "Codex pool ORM selection path failed; falling back to raw SQL",
                    exc_info=True,
                )
                return self._get_active_auth_bundle_sql(
                    db,
                    preferred_runtime_id=preferred_runtime_id,
                    allow_runtime_substitution=allow_runtime_substitution,
                    auth_service=RuntimeAuthService(),
                    excluded_runtime_ids=excluded_runtime_ids,
                )
        finally:
            db.close()

    def report_quota_exhausted(self, runtime_id: str) -> Optional[Dict[str, Any]]:
        """Mark a runtime as temporarily cooled down after quota exhaustion."""
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
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
                    candidate.extra_metadata = stamp_runtime_failure(
                        dict(getattr(candidate, "extra_metadata", None) or {}),
                        error_code="429",
                        auth_type=str(getattr(candidate, "auth_type", "") or ""),
                        failure_scope_key=(
                            f"quota:{quota_scope_key}" if quota_scope_key else f"runtime:{candidate.id}"
                        ),
                    )
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
            except Exception:
                if not hasattr(db, "execute"):
                    raise
                if hasattr(db, "rollback"):
                    db.rollback()
                logger.warning(
                    "Codex quota cooldown ORM path failed for runtime %s; falling back to raw SQL",
                    runtime_id,
                    exc_info=True,
                )
                return self._report_quota_exhausted_sql(db, runtime_id)
        finally:
            db.close()

    def report_auth_failure(
        self,
        runtime_id: str,
        *,
        error_code: str = "401",
        cooldown_seconds: int = AUTH_FAILURE_COOLDOWN_SECONDS,
    ) -> Optional[Dict[str, Any]]:
        """Temporarily cool down a runtime after an auth failure."""
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
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

                normalized_error_code = str(error_code or "401").strip() or "401"
                cooldown_value = self._auth_failure_cooldown_seconds(
                    normalized_error_code,
                    cooldown_seconds=cooldown_seconds,
                )
                cooldown_until = datetime.now(timezone.utc) + timedelta(
                    seconds=max(60, int(cooldown_value))
                )
                runtime_metadata = dict(getattr(runtime, "extra_metadata", None) or {})
                failure_scope_key = auth_failure_scope_key(
                    runtime_metadata,
                    error_code=normalized_error_code,
                    runtime_id=str(runtime_id or "").strip(),
                )
                affected_runtimes = [runtime]
                if failure_scope_key:
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
                        if self._failure_scope_key(candidate, normalized_error_code)
                        == failure_scope_key
                    ] or [runtime]

                for candidate in affected_runtimes:
                    candidate.cooldown_until = cooldown_until
                    candidate.last_error_code = normalized_error_code
                    candidate.extra_metadata = stamp_runtime_failure(
                        dict(getattr(candidate, "extra_metadata", None) or {}),
                        error_code=normalized_error_code,
                        auth_type=str(getattr(candidate, "auth_type", "") or ""),
                        failure_scope_key=failure_scope_key,
                    )
                db.commit()
                db.refresh(runtime)
                logger.warning(
                    "Codex runtime %s auth failed, cooldown %ss (error=%s affected=%s scope=%s)",
                    runtime_id,
                    max(60, int(cooldown_value)),
                    normalized_error_code,
                    len(affected_runtimes),
                    failure_scope_key or "runtime_only",
                )
                return runtime.to_dict(include_sensitive=False)
            except Exception:
                if not hasattr(db, "execute"):
                    raise
                if hasattr(db, "rollback"):
                    db.rollback()
                logger.warning(
                    "Codex auth cooldown ORM path failed for runtime %s; falling back to raw SQL",
                    runtime_id,
                    exc_info=True,
                )
                return self._report_auth_failure_sql(
                    db,
                    runtime_id,
                    error_code=str(error_code or "401"),
                    cooldown_seconds=max(60, int(cooldown_seconds)),
                )
        finally:
            db.close()

    def report_runtime_success(self, runtime_id: str) -> Optional[Dict[str, Any]]:
        """Promote a runtime back to healthy state after a verified execution success."""
        db = self._get_db()
        RuntimeEnvironment = self._get_model()
        try:
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

                runtime.cooldown_until = None
                runtime.last_error_code = None
                runtime.extra_metadata = stamp_runtime_success(
                    dict(getattr(runtime, "extra_metadata", None) or {}),
                    auth_type=str(getattr(runtime, "auth_type", "") or ""),
                )
                db.commit()
                db.refresh(runtime)
                return runtime.to_dict(include_sensitive=False)
            except Exception:
                if not hasattr(db, "execute"):
                    raise
                if hasattr(db, "rollback"):
                    db.rollback()
                logger.warning(
                    "Codex runtime success ORM path failed for runtime %s; falling back to raw SQL",
                    runtime_id,
                    exc_info=True,
                )
                return self._report_runtime_success_sql(db, runtime_id)
        finally:
            db.close()

    def _report_quota_exhausted_sql(
        self,
        db: Any,
        runtime_id: str,
    ) -> Optional[Dict[str, Any]]:
        runtime = (
            db.execute(
                text(
                    """
                    SELECT id, user_id, extra_metadata, cooldown_until, last_error_code
                    FROM runtime_environments
                    WHERE id = :runtime_id
                      AND pool_group = :pool_group
                    LIMIT 1
                    """
                ),
                {"runtime_id": runtime_id, "pool_group": CODEX_POOL_GROUP},
            )
            .mappings()
            .first()
        )
        if not runtime:
            return None

        now = datetime.now(timezone.utc)
        consecutive = self._count_recent_quota_errors_from_values(
            runtime.get("last_error_code"),
            runtime.get("cooldown_until"),
        )
        cooldown_secs = min(
            BASE_COOLDOWN_SECONDS * (BACKOFF_MULTIPLIER**consecutive),
            MAX_COOLDOWN_SECONDS,
        )
        cooldown_until = now + timedelta(seconds=cooldown_secs)
        quota_scope_key = self._quota_scope_key_from_metadata(runtime.get("extra_metadata"))
        affected_ids = [runtime_id]
        if quota_scope_key:
            sibling_rows = (
                db.execute(
                    text(
                        """
                        SELECT id, extra_metadata
                        FROM runtime_environments
                        WHERE pool_group = :pool_group
                          AND user_id = :user_id
                        """
                    ),
                    {
                        "pool_group": CODEX_POOL_GROUP,
                        "user_id": runtime.get("user_id"),
                    },
                )
                .mappings()
                .all()
            )
            affected_ids = [
                str(candidate.get("id"))
                for candidate in sibling_rows
                if self._quota_scope_key_from_metadata(candidate.get("extra_metadata"))
                == quota_scope_key
            ] or [runtime_id]

        for candidate_id in affected_ids:
            candidate_metadata = next(
                (
                    self._coerce_json_dict(candidate.get("extra_metadata"))
                    for candidate in sibling_rows
                    if str(candidate.get("id")) == candidate_id
                ),
                self._coerce_json_dict(runtime.get("extra_metadata")),
            ) if quota_scope_key else self._coerce_json_dict(runtime.get("extra_metadata"))
            updated_metadata = stamp_runtime_failure(
                candidate_metadata,
                error_code="429",
                failure_scope_key=(
                    f"quota:{quota_scope_key}" if quota_scope_key else f"runtime:{candidate_id}"
                ),
            )
            db.execute(
                text(
                    """
                    UPDATE runtime_environments
                    SET cooldown_until = :cooldown_until,
                        last_error_code = '429',
                        extra_metadata = CAST(:extra_metadata AS JSONB),
                        updated_at = NOW()
                    WHERE id = :runtime_id
                    """
                ),
                {
                    "runtime_id": candidate_id,
                    "cooldown_until": cooldown_until,
                    "extra_metadata": json.dumps(updated_metadata),
                },
            )
        db.commit()
        logger.info(
            "Codex runtime %s quota exhausted via raw SQL, cooldown %ss (consecutive=%s affected=%s scope=%s)",
            runtime_id,
            cooldown_secs,
            consecutive + 1,
            len(affected_ids),
            quota_scope_key or "runtime_only",
        )
        return {
            "id": runtime_id,
            "cooldown_until": cooldown_until.isoformat(),
            "last_error_code": "429",
        }

    def _get_active_auth_bundle_sql(
        self,
        db: Any,
        *,
        preferred_runtime_id: Optional[str],
        allow_runtime_substitution: bool,
        auth_service: Any,
        excluded_runtime_ids: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        excluded_runtime_ids = {
            str(runtime_id).strip()
            for runtime_id in (excluded_runtime_ids or set())
            if str(runtime_id).strip()
        }
        runtimes = (
            db.execute(
                text(
                    """
                    SELECT
                        id,
                        auth_type,
                        auth_config,
                        extra_metadata,
                        pool_priority,
                        last_used_at,
                        cooldown_until,
                        last_error_code
                    FROM runtime_environments
                    WHERE pool_group = :pool_group
                      AND pool_enabled = true
                      AND auth_type IN ('api_key', 'host_session', 'none')
                      AND (cooldown_until IS NULL OR cooldown_until < :now)
                    ORDER BY pool_priority ASC, last_used_at ASC NULLS FIRST
                    """
                ),
                {
                    "pool_group": CODEX_POOL_GROUP,
                    "now": now,
                },
            )
            .mappings()
            .all()
        )
        if excluded_runtime_ids:
            runtimes = [
                runtime
                for runtime in runtimes
                if str(runtime.get("id") or "") not in excluded_runtime_ids
            ]
        runtimes = self._sort_candidate_runtime_rows(runtimes)

        if not preferred_runtime_id and not allow_runtime_substitution:
            return {
                "error": "No preferred Codex runtime configured; runtime substitution is disabled.",
                "available_runtime_count": len(runtimes),
                "available_quota_scope_count": self._count_distinct_quota_scopes_from_rows(runtimes),
            }

        if preferred_runtime_id:
            preferred = next(
                (runtime for runtime in runtimes if str(runtime.get("id")) == preferred_runtime_id),
                None,
            )
            if not preferred and not allow_runtime_substitution:
                return {
                    "error": f"Preferred Codex runtime unavailable: {preferred_runtime_id}",
                }
            if preferred:
                runtimes = [
                    preferred,
                    *[
                        runtime
                        for runtime in runtimes
                        if str(runtime.get("id")) != preferred_runtime_id
                    ],
                ]
            elif allow_runtime_substitution:
                logger.warning(
                    "Preferred Codex runtime %s unavailable in raw SQL pool selection; using ordered candidates",
                    preferred_runtime_id,
                )

        available_runtime_count = len(runtimes)
        available_quota_scope_count = self._count_distinct_quota_scopes_from_rows(runtimes)
        for runtime in runtimes:
            bundle = self._build_runtime_bundle_from_row(runtime, auth_service)
            if not bundle:
                continue
            runtime_id = str(runtime.get("id"))
            updated_metadata = stamp_runtime_selected(
                self._coerce_json_dict(runtime.get("extra_metadata")),
                auth_type=str(runtime.get("auth_type") or ""),
            )
            db.execute(
                text(
                    """
                    UPDATE runtime_environments
                    SET last_used_at = NOW(),
                        extra_metadata = CAST(:extra_metadata AS JSONB),
                        updated_at = NOW()
                    WHERE id = :runtime_id
                    """
                ),
                {
                    "runtime_id": runtime_id,
                    "extra_metadata": json.dumps(updated_metadata),
                },
            )
            db.commit()
            bundle["selected_runtime_id"] = runtime_id
            bundle["available_runtime_count"] = available_runtime_count
            bundle["available_quota_scope_count"] = available_quota_scope_count
            bundle.update(
                self._bundle_health_payload(
                    updated_metadata,
                    auth_type=str(runtime.get("auth_type") or ""),
                )
            )
            return bundle

        if preferred_runtime_id and not allow_runtime_substitution:
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

    def _report_auth_failure_sql(
        self,
        db: Any,
        runtime_id: str,
        *,
        error_code: str,
        cooldown_seconds: int,
    ) -> Optional[Dict[str, Any]]:
        runtime = (
            db.execute(
                text(
                    """
                    SELECT id, user_id, auth_type, extra_metadata
                    FROM runtime_environments
                    WHERE id = :runtime_id
                      AND pool_group = :pool_group
                    LIMIT 1
                    """
                ),
                {"runtime_id": runtime_id, "pool_group": CODEX_POOL_GROUP},
            )
            .mappings()
            .first()
        )
        if not runtime:
            return None

        normalized_error_code = str(error_code or "401").strip() or "401"
        cooldown_value = self._auth_failure_cooldown_seconds(
            normalized_error_code,
            cooldown_seconds=cooldown_seconds,
        )
        cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=cooldown_value)
        runtime_metadata = self._coerce_json_dict(runtime.get("extra_metadata"))
        failure_scope_key = auth_failure_scope_key(
            runtime_metadata,
            error_code=normalized_error_code,
            runtime_id=str(runtime_id or "").strip(),
        )

        affected_rows = [runtime]
        if failure_scope_key:
            sibling_rows = (
                db.execute(
                    text(
                        """
                        SELECT id, auth_type, extra_metadata
                        FROM runtime_environments
                        WHERE pool_group = :pool_group
                          AND user_id = :user_id
                        """
                    ),
                    {
                        "pool_group": CODEX_POOL_GROUP,
                        "user_id": runtime.get("user_id"),
                    },
                )
                .mappings()
                .all()
            )
            affected_rows = [
                candidate
                for candidate in sibling_rows
                if self._failure_scope_key_from_metadata(
                    candidate.get("extra_metadata"),
                    error_code=normalized_error_code,
                    runtime_id=str(candidate.get("id") or ""),
                )
                == failure_scope_key
            ] or [runtime]

        for candidate in affected_rows:
            updated_metadata = stamp_runtime_failure(
                self._coerce_json_dict(candidate.get("extra_metadata")),
                error_code=normalized_error_code,
                auth_type=str(candidate.get("auth_type") or ""),
                failure_scope_key=failure_scope_key,
            )
            db.execute(
                text(
                    """
                    UPDATE runtime_environments
                    SET cooldown_until = :cooldown_until,
                        last_error_code = :error_code,
                        extra_metadata = CAST(:extra_metadata AS JSONB),
                        updated_at = NOW()
                    WHERE id = :runtime_id
                    """
                ),
                {
                    "runtime_id": str(candidate.get("id") or ""),
                    "cooldown_until": cooldown_until,
                    "error_code": normalized_error_code,
                    "extra_metadata": json.dumps(updated_metadata),
                },
            )
        db.commit()
        logger.warning(
            "Codex runtime %s auth failed via raw SQL, cooldown %ss (error=%s affected=%s scope=%s)",
            runtime_id,
            cooldown_value,
            normalized_error_code,
            len(affected_rows),
            failure_scope_key or "runtime_only",
        )
        return {
            "id": runtime_id,
            "cooldown_until": cooldown_until.isoformat(),
            "last_error_code": normalized_error_code,
        }

    def _report_runtime_success_sql(
        self,
        db: Any,
        runtime_id: str,
    ) -> Optional[Dict[str, Any]]:
        runtime = (
            db.execute(
                text(
                    """
                    SELECT id, auth_type, extra_metadata
                    FROM runtime_environments
                    WHERE id = :runtime_id
                      AND pool_group = :pool_group
                    LIMIT 1
                    """
                ),
                {"runtime_id": runtime_id, "pool_group": CODEX_POOL_GROUP},
            )
            .mappings()
            .first()
        )
        if not runtime:
            return None

        updated_metadata = stamp_runtime_success(
            self._coerce_json_dict(runtime.get("extra_metadata")),
            auth_type=str(runtime.get("auth_type") or ""),
        )
        db.execute(
            text(
                """
                UPDATE runtime_environments
                SET cooldown_until = NULL,
                    last_error_code = NULL,
                    extra_metadata = CAST(:extra_metadata AS JSONB),
                    updated_at = NOW()
                WHERE id = :runtime_id
                """
            ),
            {
                "runtime_id": runtime_id,
                "extra_metadata": json.dumps(updated_metadata),
            },
        )
        db.commit()
        return {
            "id": runtime_id,
            "cooldown_until": None,
            "last_error_code": None,
        }

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
    def _build_runtime_bundle_from_row(
        cls,
        runtime: Dict[str, Any],
        auth_service: Any,
    ) -> Optional[Dict[str, Any]]:
        auth_type = str(runtime.get("auth_type") or "none").strip().lower()
        if auth_type == "api_key":
            auth_config = cls._coerce_json_dict(runtime.get("auth_config"))
            try:
                decrypted = auth_service.decrypt_credentials(auth_config)
            except Exception:
                logger.exception(
                    "Failed to decrypt Codex API key for runtime %s via raw SQL path",
                    runtime.get("id"),
                )
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
            metadata = cls._coerce_json_dict(runtime.get("extra_metadata"))
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
        return CodexPoolService._count_recent_quota_errors_from_values(
            getattr(runtime, "last_error_code", None),
            getattr(runtime, "cooldown_until", None),
        )

    @staticmethod
    def _count_recent_quota_errors_from_values(
        last_error_code: Any,
        cooldown_until: Any,
    ) -> int:
        if str(last_error_code or "") != "429":
            return 0
        if not cooldown_until:
            return 0
        if isinstance(cooldown_until, str):
            try:
                cooldown_until = datetime.fromisoformat(
                    cooldown_until.replace("Z", "+00:00")
                )
            except ValueError:
                return 0
        if getattr(cooldown_until, "tzinfo", None) is None:
            cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
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

    @staticmethod
    def _quota_scope_key_from_metadata(metadata: Any) -> Optional[str]:
        metadata = CodexPoolService._coerce_json_dict(metadata)
        value = str(metadata.get("quota_scope_key") or "").strip()
        return value or None

    @classmethod
    def _count_distinct_quota_scopes(cls, runtimes: list[Any]) -> int:
        scopes = {
            cls._quota_scope_key(runtime) or f"runtime:{getattr(runtime, 'id', '')}"
            for runtime in runtimes
        }
        return len(scopes)

    @classmethod
    def _count_distinct_quota_scopes_from_rows(cls, runtimes: list[Dict[str, Any]]) -> int:
        scopes = {
            cls._quota_scope_key_from_metadata(runtime.get("extra_metadata"))
            or f"runtime:{runtime.get('id')}"
            for runtime in runtimes
        }
        return len(scopes)

    @classmethod
    def _sort_candidate_runtimes(cls, runtimes: list[Any]) -> list[Any]:
        return sorted(
            runtimes,
            key=lambda runtime: cls._candidate_sort_key_from_values(
                auth_type=str(getattr(runtime, "auth_type", "") or ""),
                metadata=dict(getattr(runtime, "extra_metadata", None) or {}),
                pool_priority=getattr(runtime, "pool_priority", 0),
                last_used_at=getattr(runtime, "last_used_at", None),
                last_error_code=getattr(runtime, "last_error_code", None),
            ),
        )

    @classmethod
    def _sort_candidate_runtime_rows(cls, runtimes: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        return sorted(
            runtimes,
            key=lambda runtime: cls._candidate_sort_key_from_values(
                auth_type=str(runtime.get("auth_type") or ""),
                metadata=cls._coerce_json_dict(runtime.get("extra_metadata")),
                pool_priority=runtime.get("pool_priority"),
                last_used_at=runtime.get("last_used_at"),
                last_error_code=runtime.get("last_error_code"),
            ),
        )

    @classmethod
    def _candidate_sort_key_from_values(
        cls,
        *,
        auth_type: str,
        metadata: Dict[str, Any],
        pool_priority: Any,
        last_used_at: Any,
        last_error_code: Any,
    ) -> tuple[Any, ...]:
        health = read_health_metadata(metadata, auth_type=auth_type)
        last_success_at = coerce_datetime(health.get("last_success_at"))
        last_used_dt = coerce_datetime(last_used_at)
        return (
            health_state_rank(str(health.get("health_state") or "")),
            seed_kind_rank(str(health.get("seed_kind") or "")),
            0 if last_success_at else 1,
            -(last_success_at.timestamp()) if last_success_at else 0.0,
            int(pool_priority or 0),
            0 if last_used_dt is None else 1,
            last_used_dt or datetime.min.replace(tzinfo=timezone.utc),
            0 if not str(last_error_code or "").strip() else 1,
        )

    @classmethod
    def _bundle_health_payload(
        cls,
        metadata: Dict[str, Any],
        *,
        auth_type: str,
    ) -> Dict[str, Any]:
        health = read_health_metadata(metadata, auth_type=auth_type)
        return {
            "runtime_seed_kind": health.get("seed_kind"),
            "runtime_health_state": health.get("health_state"),
            "runtime_failure_scope_key": health.get("failure_scope_key"),
        }

    @classmethod
    def _failure_scope_key(cls, runtime: Any, error_code: str) -> Optional[str]:
        return auth_failure_scope_key(
            dict(getattr(runtime, "extra_metadata", None) or {}),
            error_code=error_code,
            runtime_id=str(getattr(runtime, "id", "") or ""),
        )

    @classmethod
    def _failure_scope_key_from_metadata(
        cls,
        metadata: Any,
        *,
        error_code: str,
        runtime_id: str,
    ) -> Optional[str]:
        return auth_failure_scope_key(
            cls._coerce_json_dict(metadata),
            error_code=error_code,
            runtime_id=runtime_id,
        )

    @staticmethod
    def _auth_failure_cooldown_seconds(error_code: str, *, cooldown_seconds: int) -> int:
        normalized = str(error_code or "").strip().lower()
        if normalized in {"timeout", "stall"}:
            return BASE_COOLDOWN_SECONDS
        return max(60, int(cooldown_seconds))

    @staticmethod
    def _coerce_json_dict(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _run_due_requalification() -> None:
        from backend.app.services.codex_pool_requalification_service import (
            CodexPoolRequalificationService,
        )

        CodexPoolRequalificationService().sweep_due_runtimes()
