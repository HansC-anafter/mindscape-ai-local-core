"""
Codex CLI runtime pool service.

Supports rotating across multiple Codex runtimes backed by either:
- API keys
- Host sessions isolated via runtime metadata (for example CODEX_HOME)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy import or_
from sqlalchemy.sql import func

from . import codex_pool_runtime_bundle as runtime_bundle
from . import codex_pool_sql_paths as sql_paths
from .codex_pool_health import (
    auth_failure_scope_key,
    coerce_datetime,
    stamp_runtime_failure,
    stamp_runtime_probe_failure,
    stamp_runtime_probe_success,
    stamp_runtime_selected,
    stamp_runtime_success,
)

logger = logging.getLogger(__name__)

CODEX_POOL_GROUP = runtime_bundle.CODEX_POOL_GROUP
BASE_COOLDOWN_SECONDS = runtime_bundle.BASE_COOLDOWN_SECONDS
MAX_COOLDOWN_SECONDS = runtime_bundle.MAX_COOLDOWN_SECONDS
BACKOFF_MULTIPLIER = runtime_bundle.BACKOFF_MULTIPLIER
AUTH_FAILURE_COOLDOWN_SECONDS = runtime_bundle.AUTH_FAILURE_COOLDOWN_SECONDS


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
        excluded_runtime_ids: Optional[set[str]] = None,
        excluded_quota_scope_keys: Optional[set[str]] = None,
        require_probe_available: bool = False,
    ) -> Dict[str, Any]:
        """Return env/auth metadata for the best available Codex runtime."""
        if allow_runtime_substitution is None:
            allow_runtime_substitution = False
        else:
            allow_runtime_substitution = bool(allow_runtime_substitution)
        excluded_runtime_ids = {
            str(runtime_id).strip()
            for runtime_id in (excluded_runtime_ids or set())
            if str(runtime_id).strip()
        }
        excluded_quota_scope_keys = {
            str(scope_key).strip()
            for scope_key in (excluded_quota_scope_keys or set())
            if str(scope_key).strip()
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
                if excluded_quota_scope_keys:
                    runtimes = [
                        runtime
                        for runtime in runtimes
                        if (
                            self._quota_scope_key(runtime)
                            or f"runtime:{getattr(runtime, 'id', '')}"
                        )
                        not in excluded_quota_scope_keys
                    ]
                runtimes = self._filter_runnable_candidate_runtimes(
                    runtimes,
                    require_probe_available=require_probe_available,
                )
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
                    bundle["quota_scope_key"] = self._quota_scope_key(runtime)
                    bundle["runtime_account_identity"] = (
                        self._runtime_account_identity_payload(
                            dict(getattr(runtime, "extra_metadata", None) or {})
                        )
                    )
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
                    excluded_quota_scope_keys=excluded_quota_scope_keys,
                    require_probe_available=require_probe_available,
                )
        finally:
            db.close()

    def report_quota_exhausted(
        self,
        runtime_id: str,
        *,
        reset_at: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
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
                reset_until = coerce_datetime(reset_at)
                if reset_until and reset_until > cooldown_until:
                    cooldown_until = reset_until
                    cooldown_secs = max(1, int((cooldown_until - now).total_seconds()))
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
                    candidate.extra_metadata = stamp_runtime_probe_failure(
                        dict(getattr(candidate, "extra_metadata", None) or {}),
                        error_code="429",
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
                return self._report_quota_exhausted_sql(
                    db,
                    runtime_id,
                    reset_at=reset_at,
                )
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
                    candidate.extra_metadata = stamp_runtime_probe_failure(
                        dict(getattr(candidate, "extra_metadata", None) or {}),
                        error_code=normalized_error_code,
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
                runtime.extra_metadata = stamp_runtime_probe_success(
                    dict(getattr(runtime, "extra_metadata", None) or {}),
                    returncode=0,
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

    _truthy_metadata_value = staticmethod(runtime_bundle.truthy_metadata_value)
    _report_quota_exhausted_sql = staticmethod(sql_paths.report_quota_exhausted_sql)
    _get_active_auth_bundle_sql = staticmethod(sql_paths.get_active_auth_bundle_sql)
    _report_auth_failure_sql = staticmethod(sql_paths.report_auth_failure_sql)
    _report_runtime_success_sql = staticmethod(sql_paths.report_runtime_success_sql)
    _build_runtime_bundle = staticmethod(runtime_bundle.build_runtime_bundle)
    _build_runtime_bundle_from_row = staticmethod(runtime_bundle.build_runtime_bundle_from_row)
    _host_session_env_from_metadata = staticmethod(runtime_bundle.host_session_env_from_metadata)
    _count_recent_quota_errors = staticmethod(runtime_bundle.count_recent_quota_errors)
    _count_recent_quota_errors_from_values = staticmethod(runtime_bundle.count_recent_quota_errors_from_values)
    _quota_scope_key = staticmethod(runtime_bundle.quota_scope_key)
    _quota_scope_key_from_metadata = staticmethod(runtime_bundle.quota_scope_key_from_metadata)
    _runtime_account_identity_payload = staticmethod(runtime_bundle.runtime_account_identity_payload)
    _count_distinct_quota_scopes = staticmethod(runtime_bundle.count_distinct_quota_scopes)
    _count_distinct_quota_scopes_from_rows = staticmethod(runtime_bundle.count_distinct_quota_scopes_from_rows)
    _filter_runnable_candidate_runtimes = staticmethod(runtime_bundle.filter_runnable_candidate_runtimes)
    _filter_runnable_candidate_runtime_rows = staticmethod(runtime_bundle.filter_runnable_candidate_runtime_rows)
    _is_runnable_candidate = staticmethod(runtime_bundle.is_runnable_candidate)
    _sort_candidate_runtimes = staticmethod(runtime_bundle.sort_candidate_runtimes)
    _sort_candidate_runtime_rows = staticmethod(runtime_bundle.sort_candidate_runtime_rows)
    _candidate_sort_key_from_values = staticmethod(runtime_bundle.candidate_sort_key_from_values)
    _bundle_health_payload = staticmethod(runtime_bundle.bundle_health_payload)
    _failure_scope_key = staticmethod(runtime_bundle.failure_scope_key)
    _failure_scope_key_from_metadata = staticmethod(runtime_bundle.failure_scope_key_from_metadata)
    _auth_failure_cooldown_seconds = staticmethod(runtime_bundle.auth_failure_cooldown_seconds)
    _coerce_json_dict = staticmethod(runtime_bundle.coerce_json_dict)

    @staticmethod
    def _run_due_requalification() -> None:
        from backend.app.services.codex_pool_requalification_service import (
            CodexPoolRequalificationService,
        )

        CodexPoolRequalificationService().sweep_due_runtimes()
