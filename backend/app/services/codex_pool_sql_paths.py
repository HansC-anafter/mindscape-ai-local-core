"""
Raw SQL fallback paths for the Codex CLI runtime pool.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from .codex_pool_health import (
    auth_failure_scope_key,
    coerce_datetime,
    stamp_runtime_failure,
    stamp_runtime_probe_failure,
    stamp_runtime_probe_success,
    stamp_runtime_selected,
    stamp_runtime_success,
)
from .codex_pool_runtime_bundle import (
    BACKOFF_MULTIPLIER,
    BASE_COOLDOWN_SECONDS,
    CODEX_POOL_GROUP,
    MAX_COOLDOWN_SECONDS,
    auth_failure_cooldown_seconds,
    build_runtime_bundle_from_row,
    bundle_health_payload,
    coerce_json_dict,
    count_distinct_quota_scopes_from_rows,
    count_recent_quota_errors_from_values,
    failure_scope_key_from_metadata,
    filter_runnable_candidate_runtime_rows,
    quota_scope_key_from_metadata,
    runtime_account_identity_payload,
    sort_candidate_runtime_rows,
)

logger = logging.getLogger(__name__)


def report_quota_exhausted_sql(
    db: Any,
    runtime_id: str,
    *,
    reset_at: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    runtime = (
        db.execute(
            text(
                """
                SELECT id, user_id, auth_type, extra_metadata, cooldown_until, last_error_code
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
    consecutive = count_recent_quota_errors_from_values(
        runtime.get("last_error_code"),
        runtime.get("cooldown_until"),
    )
    cooldown_secs = min(
        BASE_COOLDOWN_SECONDS * (BACKOFF_MULTIPLIER**consecutive),
        MAX_COOLDOWN_SECONDS,
    )
    cooldown_until = now + timedelta(seconds=cooldown_secs)
    reset_until = coerce_datetime(reset_at)
    if reset_until and reset_until > cooldown_until:
        cooldown_until = reset_until
        cooldown_secs = max(1, int((cooldown_until - now).total_seconds()))
    quota_scope_key = quota_scope_key_from_metadata(runtime.get("extra_metadata"))
    affected_ids = [runtime_id]
    if quota_scope_key:
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
        affected_ids = [
            str(candidate.get("id"))
            for candidate in sibling_rows
            if quota_scope_key_from_metadata(candidate.get("extra_metadata"))
            == quota_scope_key
        ] or [runtime_id]

    for candidate_id in affected_ids:
        candidate_row = None
        if quota_scope_key:
            candidate_row = next(
                (
                    candidate
                    for candidate in sibling_rows
                    if str(candidate.get("id")) == candidate_id
                ),
                None,
            )
        candidate_metadata = coerce_json_dict(
            (candidate_row or runtime).get("extra_metadata")
        )
        updated_metadata = stamp_runtime_failure(
            candidate_metadata,
            error_code="429",
            auth_type=str((candidate_row or runtime).get("auth_type") or ""),
            failure_scope_key=(
                f"quota:{quota_scope_key}" if quota_scope_key else f"runtime:{candidate_id}"
            ),
        )
        updated_metadata = stamp_runtime_probe_failure(
            updated_metadata,
            error_code="429",
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


def get_active_auth_bundle_sql(
    db: Any,
    *,
    preferred_runtime_id: Optional[str],
    allow_runtime_substitution: bool,
    auth_service: Any,
    excluded_runtime_ids: Optional[set[str]] = None,
    excluded_quota_scope_keys: Optional[set[str]] = None,
    require_probe_available: bool = False,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
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
    if excluded_quota_scope_keys:
        runtimes = [
            runtime
            for runtime in runtimes
            if (
                quota_scope_key_from_metadata(runtime.get("extra_metadata"))
                or f"runtime:{runtime.get('id')}"
            )
            not in excluded_quota_scope_keys
        ]
    runtimes = filter_runnable_candidate_runtime_rows(
        runtimes,
        require_probe_available=require_probe_available,
    )
    runtimes = sort_candidate_runtime_rows(runtimes)

    if not preferred_runtime_id and not allow_runtime_substitution:
        return {
            "error": "No preferred Codex runtime configured; runtime substitution is disabled.",
            "available_runtime_count": len(runtimes),
            "available_quota_scope_count": count_distinct_quota_scopes_from_rows(runtimes),
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
    available_quota_scope_count = count_distinct_quota_scopes_from_rows(runtimes)
    for runtime in runtimes:
        bundle = build_runtime_bundle_from_row(runtime, auth_service)
        if not bundle:
            continue
        runtime_id = str(runtime.get("id"))
        updated_metadata = stamp_runtime_selected(
            coerce_json_dict(runtime.get("extra_metadata")),
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
        bundle["quota_scope_key"] = quota_scope_key_from_metadata(
            runtime.get("extra_metadata")
        )
        bundle["runtime_account_identity"] = runtime_account_identity_payload(
            runtime.get("extra_metadata")
        )
        bundle.update(
            bundle_health_payload(
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


def report_auth_failure_sql(
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
    cooldown_value = auth_failure_cooldown_seconds(
        normalized_error_code,
        cooldown_seconds=cooldown_seconds,
    )
    cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=cooldown_value)
    runtime_metadata = coerce_json_dict(runtime.get("extra_metadata"))
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
            if failure_scope_key_from_metadata(
                candidate.get("extra_metadata"),
                error_code=normalized_error_code,
                runtime_id=str(candidate.get("id") or ""),
            )
            == failure_scope_key
        ] or [runtime]

    for candidate in affected_rows:
        updated_metadata = stamp_runtime_failure(
            coerce_json_dict(candidate.get("extra_metadata")),
            error_code=normalized_error_code,
            auth_type=str(candidate.get("auth_type") or ""),
            failure_scope_key=failure_scope_key,
        )
        updated_metadata = stamp_runtime_probe_failure(
            updated_metadata,
            error_code=normalized_error_code,
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


def report_runtime_success_sql(
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
        coerce_json_dict(runtime.get("extra_metadata")),
        auth_type=str(runtime.get("auth_type") or ""),
    )
    updated_metadata = stamp_runtime_probe_success(
        updated_metadata,
        returncode=0,
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
