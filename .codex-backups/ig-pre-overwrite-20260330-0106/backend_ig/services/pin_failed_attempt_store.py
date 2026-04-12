import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import bindparam, text

from app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _normalize_handle(value: Optional[str]) -> str:
    return _normalize_text(value).lstrip("@").lower()


def _build_identity(
    *,
    source_shortcode: Optional[str],
    source_url: Optional[str],
    image_url: Optional[str],
) -> str:
    shortcode = _normalize_text(source_shortcode)
    if shortcode:
        return f"shortcode:{shortcode.lower()}"
    source = _normalize_text(source_url)
    if source:
        return f"source_url:{source}"
    image = _normalize_text(image_url)
    if image:
        return f"image_url:{image}"
    return "unknown"


def build_pin_failed_attempt_dedupe_key(
    *,
    workspace_id: str,
    source_handle: Optional[str],
    source_shortcode: Optional[str],
    source_url: Optional[str],
    image_url: Optional[str],
) -> str:
    raw = "|".join(
        [
            _normalize_text(workspace_id),
            _normalize_handle(source_handle),
            _build_identity(
                source_shortcode=source_shortcode,
                source_url=source_url,
                image_url=image_url,
            ),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


class PostgresIGPinFailedAttemptStore(PostgresStoreBase):
    def list_attempts(
        self,
        *,
        workspace_id: str,
        source_handle: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        normalized_workspace_id = _normalize_text(workspace_id)
        normalized_handle = _normalize_handle(source_handle) if source_handle else None
        normalized_status = _normalize_text(status).lower() or None

        where_sql = ["workspace_id = :workspace_id"]
        params: Dict[str, Any] = {
            "workspace_id": normalized_workspace_id,
            "limit": int(limit),
            "offset": int(offset),
        }

        if normalized_handle:
            where_sql.append("lower(coalesce(source_handle, '')) = :source_handle")
            params["source_handle"] = normalized_handle

        if normalized_status:
            where_sql.append("lower(status) = :status")
            params["status"] = normalized_status

        filter_sql = " WHERE " + " AND ".join(where_sql)

        total_query = text(f"SELECT COUNT(*) FROM ig_pin_failed_attempts{filter_sql}")
        list_query = text(
            f"""
            SELECT *
            FROM ig_pin_failed_attempts
            {filter_sql}
            ORDER BY last_failed_at DESC, created_at DESC
            LIMIT :limit OFFSET :offset
            """
        )

        with self.get_connection() as conn:
            total = int(conn.execute(total_query, params).scalar() or 0)
            rows = conn.execute(list_query, params).mappings().all()

        return [dict(row) for row in rows], total

    def list_retry_candidates(
        self,
        *,
        workspace_id: str,
        source_handle: Optional[str] = None,
        dedupe_keys: Optional[Sequence[str]] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        normalized_workspace_id = _normalize_text(workspace_id)
        normalized_handle = _normalize_handle(source_handle) if source_handle else None
        normalized_keys = [key.strip() for key in (dedupe_keys or []) if str(key).strip()]

        where_sql = [
            "workspace_id = :workspace_id",
            "lower(status) IN ('pending_retry', 'retrying')",
        ]
        params: Dict[str, Any] = {
            "workspace_id": normalized_workspace_id,
            "limit": int(limit),
        }

        if normalized_handle:
            where_sql.append("lower(coalesce(source_handle, '')) = :source_handle")
            params["source_handle"] = normalized_handle

        base_query = """
            SELECT *
            FROM ig_pin_failed_attempts
            WHERE {where_sql}
        """

        if normalized_keys:
            where_sql.append("dedupe_key IN :dedupe_keys")
            query = text(
                base_query.format(where_sql=" AND ".join(where_sql))
                + """
                ORDER BY last_failed_at DESC, created_at DESC
                LIMIT :limit
                """
            ).bindparams(bindparam("dedupe_keys", expanding=True))
            params["dedupe_keys"] = normalized_keys
        else:
            query = text(
                base_query.format(where_sql=" AND ".join(where_sql))
                + """
                ORDER BY last_failed_at DESC, created_at DESC
                LIMIT :limit
                """
            )

        with self.get_connection() as conn:
            rows = conn.execute(query, params).mappings().all()

        return [dict(row) for row in rows]

    def record_failed_attempt(
        self,
        *,
        workspace_id: str,
        source_handle: Optional[str],
        source_shortcode: Optional[str],
        source_url: Optional[str],
        image_url: Optional[str],
        parent_execution_id: Optional[str],
        trigger: Optional[str],
        error_kind: str,
        error_message: str,
        base64_image_present: bool,
        failure_payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        dedupe_key = build_pin_failed_attempt_dedupe_key(
            workspace_id=workspace_id,
            source_handle=source_handle,
            source_shortcode=source_shortcode,
            source_url=source_url,
            image_url=image_url,
        )
        now = _utc_now()
        payload_json = json.dumps(failure_payload or {})

        params = {
            "id": str(uuid.uuid4()),
            "dedupe_key": dedupe_key,
            "workspace_id": _normalize_text(workspace_id),
            "source_handle": _normalize_text(source_handle) or None,
            "source_shortcode": _normalize_text(source_shortcode) or None,
            "source_url": _normalize_text(source_url) or None,
            "image_url": _normalize_text(image_url) or None,
            "parent_execution_id": _normalize_text(parent_execution_id) or None,
            "trigger": _normalize_text(trigger) or None,
            "base64_image_present": bool(base64_image_present),
            "error_kind": _normalize_text(error_kind) or "pin_error",
            "error_message": _normalize_text(error_message) or "Unknown pin error",
            "failure_payload": payload_json,
            "status": "pending_retry",
            "failure_count": 1,
            "first_failed_at": now,
            "last_failed_at": now,
            "created_at": now,
            "updated_at": now,
        }

        query = text(
            """
            INSERT INTO ig_pin_failed_attempts (
                id,
                dedupe_key,
                workspace_id,
                source_handle,
                source_shortcode,
                source_url,
                image_url,
                parent_execution_id,
                trigger,
                base64_image_present,
                error_kind,
                error_message,
                failure_payload,
                status,
                failure_count,
                first_failed_at,
                last_failed_at,
                created_at,
                updated_at
            ) VALUES (
                :id,
                :dedupe_key,
                :workspace_id,
                :source_handle,
                :source_shortcode,
                :source_url,
                :image_url,
                :parent_execution_id,
                :trigger,
                :base64_image_present,
                :error_kind,
                :error_message,
                CAST(:failure_payload AS JSONB),
                :status,
                :failure_count,
                :first_failed_at,
                :last_failed_at,
                :created_at,
                :updated_at
            )
            ON CONFLICT (dedupe_key) DO UPDATE SET
                source_url = COALESCE(EXCLUDED.source_url, ig_pin_failed_attempts.source_url),
                image_url = COALESCE(EXCLUDED.image_url, ig_pin_failed_attempts.image_url),
                parent_execution_id = COALESCE(EXCLUDED.parent_execution_id, ig_pin_failed_attempts.parent_execution_id),
                trigger = COALESCE(EXCLUDED.trigger, ig_pin_failed_attempts.trigger),
                base64_image_present = ig_pin_failed_attempts.base64_image_present OR EXCLUDED.base64_image_present,
                error_kind = EXCLUDED.error_kind,
                error_message = EXCLUDED.error_message,
                failure_payload = EXCLUDED.failure_payload,
                status = 'pending_retry',
                failure_count = ig_pin_failed_attempts.failure_count + 1,
                last_failed_at = EXCLUDED.last_failed_at,
                updated_at = EXCLUDED.updated_at,
                recovered_at = NULL,
                recovered_reference_id = NULL
            """
        )

        with self.transaction() as conn:
            conn.execute(query, params)

        return dedupe_key

    def mark_recovered(
        self,
        *,
        workspace_id: str,
        source_handle: Optional[str],
        source_shortcode: Optional[str],
        source_url: Optional[str],
        image_url: Optional[str],
        reference_id: Optional[str],
    ) -> bool:
        dedupe_key = build_pin_failed_attempt_dedupe_key(
            workspace_id=workspace_id,
            source_handle=source_handle,
            source_shortcode=source_shortcode,
            source_url=source_url,
            image_url=image_url,
        )
        now = _utc_now()
        query = text(
            """
            UPDATE ig_pin_failed_attempts
            SET status = 'recovered',
                recovered_at = :recovered_at,
                recovered_reference_id = :recovered_reference_id,
                updated_at = :updated_at
            WHERE dedupe_key = :dedupe_key
              AND status <> 'recovered'
            """
        )
        with self.transaction() as conn:
            result = conn.execute(
                query,
                {
                    "dedupe_key": dedupe_key,
                    "recovered_at": now,
                    "recovered_reference_id": _normalize_text(reference_id) or None,
                    "updated_at": now,
                },
            )
        return bool(result.rowcount)
