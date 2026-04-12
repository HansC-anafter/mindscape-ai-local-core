"""
IG Insights API

Query endpoints for profile tags, posts, network analysis, personas, and seed management.
Provides read-only access to data computed by IG enhancement tools.
"""

import logging
from datetime import datetime, timezone
import json


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from capabilities.ig.source_filters import confirmed_target_condition_sql
from capabilities.ig.services.confirmed_targets import (
    load_confirmed_targets_total,
    normalize_target_handle,
    should_use_confirmed_targets_total_fast_path,
    upsert_confirmed_target_handles,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IG Insights"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProfileTagRow(BaseModel):
    id: Optional[str] = None
    account_handle: str
    account_type: Optional[str] = None
    influence_tier: Optional[str] = None
    engagement_potential: Optional[float] = None
    follower_following_ratio: Optional[float] = None
    bio_keywords_json: Optional[str] = None
    bio_detected_locale: Optional[str] = None
    computed_at: Optional[str] = None


class PostRow(BaseModel):
    id: Optional[str] = None
    account_handle: str
    post_shortcode: Optional[str] = None
    post_type: Optional[str] = None
    post_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    caption: Optional[str] = None
    hashtags_json: Optional[str] = None  # Fixed: was caption_hashtags_json
    caption_topic: Optional[str] = None
    caption_sentiment: Optional[str] = None
    posted_at: Optional[str] = None
    captured_at: Optional[str] = None


class NetworkOverlap(BaseModel):
    target_handle: str
    overlap_count: int
    shared_by: List[str]


class PersonaRow(BaseModel):
    id: Optional[str] = None
    account_handle: str
    persona_summary: Optional[str] = None
    persona_locale: Optional[str] = None  # Fixed: was persona_summary_locale
    key_traits_json: Optional[str] = None
    content_themes_json: Optional[str] = None
    demographics_json: Optional[str] = None  # Fixed: was estimated_demographics_json
    collaboration_potential: Optional[float] = None
    recommended_approach: Optional[str] = None
    generated_at: Optional[str] = None


class SeedExecutionSummary(BaseModel):
    execution_id: Optional[str] = None
    status: Optional[str] = None
    queue_position: Optional[int] = None
    blocked_reason: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class SeedInfo(BaseModel):
    seed: str
    target_count: int
    visited_count: int = 0
    expected_count: Optional[int] = None
    bio: Optional[str] = None
    profile_picture_url: Optional[str] = None
    last_crawled: Optional[str] = None
    has_tags: bool = False
    has_posts: bool = False
    has_network: bool = False
    has_personas: bool = False
    execution: Optional[SeedExecutionSummary] = None


class SeedListResponse(BaseModel):
    seeds: List[SeedInfo]
    total: int


class BatchPinMetrics(BaseModel):
    collected_count: Optional[int] = None
    pinned_count: Optional[int] = None
    duplicate_count: Optional[int] = None
    failed_count: Optional[int] = None
    target_count: Optional[int] = None
    existing_reference_count_before: Optional[int] = None
    existing_reference_count_after: Optional[int] = None
    remaining_needed_before: Optional[int] = None
    remaining_to_target: Optional[int] = None
    target_met: Optional[bool] = None


class BatchPinExecutionSummary(BaseModel):
    execution_id: str
    status: str
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    target_count: Optional[int] = None
    user_data_dir: Optional[str] = None
    metrics: Optional[BatchPinMetrics] = None


class LatestBatchPinSummaryResponse(BaseModel):
    latest_attempt: Optional[BatchPinExecutionSummary] = None
    latest_completed: Optional[BatchPinExecutionSummary] = None


class PinFailedAttemptRow(BaseModel):
    id: str
    dedupe_key: str
    workspace_id: str
    source_handle: Optional[str] = None
    source_shortcode: Optional[str] = None
    source_url: Optional[str] = None
    image_url: Optional[str] = None
    parent_execution_id: Optional[str] = None
    trigger: Optional[str] = None
    base64_image_present: bool = False
    error_kind: str
    error_message: str
    status: str
    failure_count: int
    first_failed_at: Optional[str] = None
    last_failed_at: Optional[str] = None
    recovered_at: Optional[str] = None
    recovered_reference_id: Optional[str] = None
    failure_payload: Optional[Dict[str, Any]] = None


class PinFailedAttemptListResponse(BaseModel):
    attempts: List[PinFailedAttemptRow]
    total: int


class RetryPinFailedAttemptsRequest(BaseModel):
    handle: Optional[str] = None
    dedupe_keys: List[str] = Field(default_factory=list)
    limit: int = Field(default=25, ge=1, le=100)
    pinned_by: Optional[str] = None


class RetryPinFailedAttemptsResult(BaseModel):
    dedupe_key: str
    source_shortcode: Optional[str] = None
    status: str
    final_disposition: Optional[str] = None
    reference_id: Optional[str] = None
    error_kind: Optional[str] = None
    error: Optional[str] = None


class RetryPinFailedAttemptsResponse(BaseModel):
    retried: int
    recovered: int
    still_failed: int
    results: List[RetryPinFailedAttemptsResult]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _get_connection():
    from app.database.engine import engine_postgres_core

    return engine_postgres_core.connect()


def _table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database."""
    from sqlalchemy import text

    result = conn.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
        ),
        {"t": table_name},
    )
    row = result.fetchone()
    return bool(row and row[0])


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    from sqlalchemy import text

    result = conn.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c)"
        ),
        {"t": table_name, "c": column_name},
    )
    row = result.fetchone()
    return bool(row and row[0])


def _safe_count(conn, query: str, params: dict) -> int:
    """Execute a count query safely, returning 0 on any error."""
    from sqlalchemy import text

    try:
        result = conn.execute(text(query), params)
        row = result.fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def _normalize_ig_handle(value: Optional[str]) -> str:
    return normalize_target_handle(value)


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _extract_batch_pin_metrics(execution_context: Any) -> Optional[BatchPinMetrics]:
    if not isinstance(execution_context, dict):
        return None

    workflow_result = execution_context.get("workflow_result")
    if not isinstance(workflow_result, dict):
        return None

    candidates: List[Any] = [
        (
            workflow_result.get("context", {})
            if isinstance(workflow_result.get("context"), dict)
            else {}
        ).get("ig_batch_pin_references", {})
        if isinstance(
            (
                workflow_result.get("context", {})
                if isinstance(workflow_result.get("context"), dict)
                else {}
            ).get("ig_batch_pin_references"),
            dict,
        )
        else None,
        workflow_result.get("batch_pin"),
    ]

    payload = None
    for candidate in candidates:
        if isinstance(candidate, dict) and isinstance(candidate.get("batch_pin"), dict):
            payload = candidate.get("batch_pin")
            break
        if isinstance(candidate, dict) and any(
            key in candidate
            for key in (
                "collected_count",
                "pinned_count",
                "duplicate_count",
                "existing_reference_count_after",
                "remaining_to_target",
            )
        ):
            payload = candidate
            break

    if not isinstance(payload, dict):
        return None

    return BatchPinMetrics(
        collected_count=_coerce_int(payload.get("collected_count")),
        pinned_count=_coerce_int(payload.get("pinned_count")),
        duplicate_count=_coerce_int(payload.get("duplicate_count")),
        failed_count=_coerce_int(payload.get("failed_count")),
        target_count=_coerce_int(payload.get("target_count")),
        existing_reference_count_before=_coerce_int(
            payload.get("existing_reference_count_before")
        ),
        existing_reference_count_after=_coerce_int(
            payload.get("existing_reference_count_after")
        ),
        remaining_needed_before=_coerce_int(payload.get("remaining_needed_before")),
        remaining_to_target=_coerce_int(payload.get("remaining_to_target")),
        target_met=_coerce_bool(payload.get("target_met")),
    )


def _normalize_seed_status(value: Any) -> Optional[str]:
    lowered = str(value or "").strip().lower()
    if not lowered:
        return None
    if lowered in {"queued", "paused"}:
        return "pending"
    if lowered in {"succeeded", "completed"}:
        return "completed"
    if lowered in {"cancelled", "cancelled_by_user", "expired"}:
        return "failed"
    return lowered


def _build_pin_failed_attempt_row(row: Dict[str, Any]) -> PinFailedAttemptRow:
    payload = row.get("failure_payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    return PinFailedAttemptRow(
        id=str(row.get("id")),
        dedupe_key=str(row.get("dedupe_key")),
        workspace_id=str(row.get("workspace_id")),
        source_handle=row.get("source_handle"),
        source_shortcode=row.get("source_shortcode"),
        source_url=row.get("source_url"),
        image_url=row.get("image_url"),
        parent_execution_id=row.get("parent_execution_id"),
        trigger=row.get("trigger"),
        base64_image_present=bool(row.get("base64_image_present")),
        error_kind=str(row.get("error_kind") or "pin_error"),
        error_message=str(row.get("error_message") or ""),
        status=str(row.get("status") or ""),
        failure_count=int(row.get("failure_count") or 0),
        first_failed_at=str(row.get("first_failed_at")) if row.get("first_failed_at") else None,
        last_failed_at=str(row.get("last_failed_at")) if row.get("last_failed_at") else None,
        recovered_at=str(row.get("recovered_at")) if row.get("recovered_at") else None,
        recovered_reference_id=row.get("recovered_reference_id"),
        failure_payload=payload or None,
    )


def _load_seed_execution_summaries(conn, workspace_id: str, seed_map: Dict[str, SeedInfo]) -> None:
    from sqlalchemy import bindparam, text

    normalized_seed_lookup = {
        _normalize_ig_handle(seed.seed): seed for seed in seed_map.values() if _normalize_ig_handle(seed.seed)
    }
    if not normalized_seed_lookup:
        return

    pending_queue_query = text(
        """
        SELECT
            id,
            ROW_NUMBER() OVER (
                ORDER BY next_eligible_at ASC, created_at ASC, id ASC
            ) AS queue_position
        FROM tasks
        WHERE workspace_id = :wid
          AND pack_id = 'ig_analyze_following'
          AND lower(status) IN ('pending', 'queued', 'paused')
          AND COALESCE(next_eligible_at, created_at) <= CURRENT_TIMESTAMP
          AND COALESCE(blocked_reason, '') = ''
          AND COALESCE(frontier_state, 'ready') <> 'cold'
        """
    )
    ranked_query = text(
        """
        WITH following_tasks AS (
            SELECT
                id,
                execution_id,
                status,
                created_at,
                started_at,
                completed_at,
                error,
                blocked_reason,
                lower(ltrim(
                    coalesce(
                        execution_context->'inputs'->>'target_username',
                        execution_context->'inputs'->>'target_handle',
                        execution_context->>'target_username',
                        ''
                    ),
                    '@'
                )) AS seed_key
            FROM tasks
            WHERE workspace_id = :wid
              AND pack_id = 'ig_analyze_following'
              AND lower(ltrim(
                    coalesce(
                        execution_context->'inputs'->>'target_username',
                        execution_context->'inputs'->>'target_handle',
                        execution_context->>'target_username',
                        ''
                    ),
                    '@'
                  )) IN :seed_keys
        ),
        ranked AS (
            SELECT
                following_tasks.*,
                ROW_NUMBER() OVER (
                    PARTITION BY seed_key
                    ORDER BY
                        CASE
                            WHEN lower(status) = 'running' THEN 0
                            WHEN lower(status) IN ('pending', 'queued', 'paused') THEN 1
                            ELSE 2
                        END,
                        COALESCE(started_at, completed_at, created_at) DESC,
                        id DESC
                ) AS seed_rank
            FROM following_tasks
        )
        SELECT *
        FROM ranked
        WHERE seed_rank = 1
        """
    ).bindparams(bindparam("seed_keys", expanding=True))

    pending_rows = conn.execute(
        pending_queue_query,
        {"wid": workspace_id},
    ).mappings().all()
    pending_positions = {str(row.get("id")): int(row.get("queue_position") or 0) for row in pending_rows}

    ranked_rows = conn.execute(
        ranked_query,
        {"wid": workspace_id, "seed_keys": list(normalized_seed_lookup.keys())},
    ).mappings().all()

    for row in ranked_rows:
        seed_key = _normalize_ig_handle(row.get("seed_key"))
        seed_info = normalized_seed_lookup.get(seed_key)
        if not seed_info:
            continue
        task_id = str(row.get("id") or "")
        seed_info.execution = SeedExecutionSummary(
            execution_id=str(row.get("execution_id") or row.get("id") or ""),
            status=_normalize_seed_status(row.get("status")),
            queue_position=pending_positions.get(task_id),
            blocked_reason=row.get("blocked_reason"),
            failure_reason=row.get("error"),
            created_at=str(row.get("created_at")) if row.get("created_at") else None,
            started_at=str(row.get("started_at")) if row.get("started_at") else None,
            completed_at=str(row.get("completed_at")) if row.get("completed_at") else None,
        )


def _build_batch_pin_execution_summary(row: Any) -> Optional[BatchPinExecutionSummary]:
    if not row:
        return None

    raw_ctx = row.execution_context
    if isinstance(raw_ctx, str):
        try:
            import json

            raw_ctx = json.loads(raw_ctx)
        except Exception:
            raw_ctx = {}
    if not isinstance(raw_ctx, dict):
        raw_ctx = {}

    inputs = raw_ctx.get("inputs") if isinstance(raw_ctx.get("inputs"), dict) else {}
    metrics = _extract_batch_pin_metrics(raw_ctx)

    target_count = _coerce_int(inputs.get("target_count"))
    if target_count is None and metrics:
        target_count = metrics.target_count

    return BatchPinExecutionSummary(
        execution_id=str(row.execution_id or row.id),
        status=str(row.status or ""),
        created_at=str(row.created_at) if row.created_at else None,
        completed_at=str(row.completed_at) if row.completed_at else None,
        target_count=target_count,
        user_data_dir=(inputs.get("user_data_dir") or None),
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


@router.get("/seeds", response_model=SeedListResponse)
async def list_seeds(
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """List all known seeds with their analysis status."""
    from sqlalchemy import text

    try:
        with _get_connection() as conn:
            params = {"wid": workspace_id}

            # 1. Get unique seeds from ig_accounts_flat (single query)
            result = conn.execute(
                text(
                    """
                    SELECT seed, COUNT(*) as cnt,
                           MAX(captured_at) as last_crawled,
                           SUM(CASE WHEN follower_count IS NOT NULL THEN 1 ELSE 0 END) as visited
                    FROM ig_accounts_flat
                    WHERE workspace_id = :wid AND seed IS NOT NULL AND seed != ''
                    GROUP BY seed
                    ORDER BY last_crawled DESC
                """
                ),
                params,
            )
            rows = result.fetchall()

            if not rows:
                return SeedListResponse(seeds=[], total=0)

            # Build seed map for O(1) lookups
            seed_map: Dict[str, SeedInfo] = {}
            seeds: List[SeedInfo] = []
            for r in rows:
                info = SeedInfo(
                    seed=r[0],
                    target_count=r[1],
                    visited_count=r[3] or 0,
                    last_crawled=str(r[2]) if r[2] else None,
                )
                seed_map[r[0]] = info
                seeds.append(info)

            # 1b. Fetch expected_count + bio + profile_picture_url from seed's own row
            seed_handles = list(seed_map.keys())
            if seed_handles:
                fc_result = conn.execute(
                    text(
                        """
                        SELECT handle, following_count, bio, profile_picture_url
                        FROM ig_accounts_flat
                        WHERE workspace_id = :wid
                          AND handle = ANY(:handles)
                          AND seed = handle
                          AND (following_count IS NOT NULL OR bio IS NOT NULL OR profile_picture_url IS NOT NULL)
                        """
                    ),
                    {"wid": workspace_id, "handles": seed_handles},
                )
                for fc_row in fc_result:
                    if fc_row[0] in seed_map:
                        if fc_row[1] is not None:
                            seed_map[fc_row[0]].expected_count = fc_row[1]
                        if fc_row[2]:
                            seed_map[fc_row[0]].bio = fc_row[2]
                        if fc_row[3]:
                            seed_map[fc_row[0]].profile_picture_url = fc_row[3]

            # 2. Batch check analysis status — ONE query per table (not per seed)

            # Tags
            if _table_exists(conn, "ig_account_profiles") and _column_exists(
                conn, "ig_account_profiles", "seed"
            ):
                for r in conn.execute(
                    text(
                        "SELECT seed FROM ig_account_profiles WHERE workspace_id = :wid AND seed IS NOT NULL GROUP BY seed"
                    ),
                    params,
                ):
                    if r[0] in seed_map:
                        seed_map[r[0]].has_tags = True

            # Posts
            if _table_exists(conn, "ig_posts") and _column_exists(
                conn, "ig_posts", "seed"
            ):
                for r in conn.execute(
                    text(
                        "SELECT seed FROM ig_posts WHERE workspace_id = :wid AND seed IS NOT NULL GROUP BY seed"
                    ),
                    params,
                ):
                    if r[0] in seed_map:
                        seed_map[r[0]].has_posts = True

            # Network
            if _table_exists(conn, "ig_follow_edges") and _column_exists(
                conn, "ig_follow_edges", "discovered_via_seed"
            ):
                for r in conn.execute(
                    text(
                        "SELECT discovered_via_seed FROM ig_follow_edges WHERE workspace_id = :wid AND discovered_via_seed IS NOT NULL GROUP BY discovered_via_seed"
                    ),
                    params,
                ):
                    if r[0] in seed_map:
                        seed_map[r[0]].has_network = True

            # Personas
            if _table_exists(conn, "ig_generated_personas"):
                for r in conn.execute(
                    text(
                        """
                        SELECT DISTINCT af.seed
                        FROM ig_generated_personas gp
                        JOIN ig_accounts_flat af
                          ON af.workspace_id = gp.workspace_id
                         AND af.handle = gp.account_handle
                        WHERE gp.workspace_id = :wid
                          AND af.seed IS NOT NULL
                          AND """
                        + confirmed_target_condition_sql("af")
                        + """
                    """
                    ),
                    params,
                ):
                    if r[0] in seed_map:
                        seed_map[r[0]].has_personas = True

            _load_seed_execution_summaries(conn, workspace_id, seed_map)

            return SeedListResponse(seeds=seeds, total=len(seeds))

    except Exception as e:
        logger.error(f"[IG Insights] Failed to list seeds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seeds")
async def add_seed(
    workspace_id: str = Query(..., description="Workspace ID"),
    handle: str = Query(..., description="Instagram handle to add as seed"),
):
    """Register a handle as a seed by inserting it into ig_accounts_flat."""
    from sqlalchemy import text

    normalized_handle = _normalize_ig_handle(handle)
    if not normalized_handle:
        raise HTTPException(status_code=400, detail="Seed handle is required.")

    try:
        with _get_connection() as conn:
            # Insert a placeholder seed row immediately so the seed appears
            # before the following analyzer discovers any real accounts.
            conn.execute(
                text(
                    """
                    INSERT INTO ig_accounts_flat (
                        id,
                        workspace_id,
                        seed,
                        source_handle,
                        source_profile_ref,
                        handle,
                        name,
                        captured_at,
                        execution_id,
                        capture_method
                    ) VALUES (
                        :id,
                        :wid,
                        :seed,
                        NULL,
                        NULL,
                        :handle,
                        :name,
                        :captured_at,
                        NULL,
                        :capture_method
                    )
                    ON CONFLICT (workspace_id, seed, handle) DO UPDATE SET
                        captured_at = EXCLUDED.captured_at,
                        capture_method = EXCLUDED.capture_method
                    """
                ),
                {
                    "id": str(uuid4()),
                    "wid": workspace_id,
                    "seed": normalized_handle,
                    "handle": f"__seed_placeholder__{normalized_handle}",
                    "name": f"[Seed: {normalized_handle}]",
                    "captured_at": _utc_now().isoformat(),
                    "capture_method": "seed_registration",
                },
            )
            upsert_confirmed_target_handles(
                conn,
                workspace_id=workspace_id,
                handles=[normalized_handle],
            )
            conn.commit()

            return {
                "status": "ok",
                "message": f"Seed '{normalized_handle}' registered.",
                "handle": normalized_handle,
            }
    except Exception as e:
        logger.error(f"[IG Insights] Failed to add seed: {e}")
        raise HTTPException(status_code=500, detail="Failed to register seed.")


@router.delete("/seeds/{handle}")
async def remove_seed(
    handle: str,
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """Remove a seed and its seed-scoped crawl state."""
    from sqlalchemy import text

    normalized_handle = _normalize_ig_handle(handle)
    if not normalized_handle:
        raise HTTPException(status_code=400, detail="Seed handle is required.")

    try:
        with _get_connection() as conn:
            seed_rows_delete = conn.execute(
                text(
                    """
                    DELETE FROM ig_accounts_flat
                    WHERE workspace_id = :wid
                      AND lower(ltrim(COALESCE(seed, ''), '@')) = :seed
                    """
                ),
                {"wid": workspace_id, "seed": normalized_handle},
            )

            profile_delete_count = 0
            if _table_exists(conn, "ig_account_profiles") and _column_exists(
                conn, "ig_account_profiles", "seed"
            ):
                profile_delete = conn.execute(
                    text(
                        """
                        DELETE FROM ig_account_profiles
                        WHERE workspace_id = :wid
                          AND lower(ltrim(COALESCE(seed, ''), '@')) = :seed
                        """
                    ),
                    {"wid": workspace_id, "seed": normalized_handle},
                )
                profile_delete_count = int(profile_delete.rowcount or 0)

            edge_delete_count = 0
            if _table_exists(conn, "ig_follow_edges"):
                edge_delete = conn.execute(
                    text(
                        """
                        DELETE FROM ig_follow_edges
                        WHERE workspace_id = :wid
                          AND (
                            lower(ltrim(COALESCE(source_handle, ''), '@')) = :seed
                            OR lower(ltrim(COALESCE(discovered_via_seed, ''), '@')) = :seed
                          )
                        """
                    ),
                    {"wid": workspace_id, "seed": normalized_handle},
                )
                edge_delete_count = int(edge_delete.rowcount or 0)

            task_delete = conn.execute(
                text(
                    """
                    DELETE FROM tasks
                    WHERE workspace_id = :wid
                      AND pack_id = 'ig_analyze_following'
                      AND lower(ltrim(
                            COALESCE(
                                execution_context->'inputs'->>'target_username',
                                execution_context->'inputs'->>'target_handle',
                                execution_context->>'target_username',
                                ''
                            ),
                            '@'
                          )) = :seed
                    """
                ),
                {"wid": workspace_id, "seed": normalized_handle},
            )

            playbook_execution_delete_count = 0
            if _table_exists(conn, "playbook_executions"):
                playbook_execution_delete = conn.execute(
                    text(
                        """
                        DELETE FROM playbook_executions
                        WHERE workspace_id = :wid
                          AND playbook_code = 'ig_analyze_following'
                          AND lower(ltrim(
                                COALESCE(
                                    metadata->'inputs'->>'target_username',
                                    metadata->'inputs'->>'target_handle',
                                    metadata->>'target_username',
                                    ''
                                ),
                                '@'
                              )) = :seed
                        """
                    ),
                    {"wid": workspace_id, "seed": normalized_handle},
                )
                playbook_execution_delete_count = int(
                    playbook_execution_delete.rowcount or 0
                )

            confirmed_target_delete_count = 0
            if _table_exists(conn, "ig_confirmed_targets"):
                confirmed_target_delete = conn.execute(
                    text(
                        """
                        DELETE FROM ig_confirmed_targets
                        WHERE workspace_id = :wid
                          AND handle = :seed
                        """
                    ),
                    {"wid": workspace_id, "seed": normalized_handle},
                )
                confirmed_target_delete_count = int(
                    confirmed_target_delete.rowcount or 0
                )

            conn.commit()

            removed = {
                "seed_rows_deleted": int(seed_rows_delete.rowcount or 0),
                "profile_rows_deleted": profile_delete_count,
                "edge_rows_deleted": edge_delete_count,
                "task_rows_deleted": int(task_delete.rowcount or 0),
                "playbook_execution_rows_deleted": playbook_execution_delete_count,
                "confirmed_target_rows_deleted": confirmed_target_delete_count,
            }

            return {
                "status": "ok",
                "message": f"Seed '{normalized_handle}' removed.",
                "handle": normalized_handle,
                "removed": removed,
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "[IG Insights] Failed to remove seed %s from workspace %s: %s",
            normalized_handle,
            workspace_id,
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to remove seed.")


# ---------------------------------------------------------------------------
# Targets (single source of truth — reads from ig_accounts_flat)
# ---------------------------------------------------------------------------


class TargetRow(BaseModel):
    handle: str
    name: Optional[str] = None
    bio: Optional[str] = None
    profile_picture_url: Optional[str] = None
    follower_count: Optional[int] = None
    following_count: Optional[int] = None
    post_count: Optional[int] = None
    external_url: Optional[str] = None
    is_verified: Optional[bool] = None
    is_private: Optional[bool] = None
    category: Optional[str] = None
    public_email: Optional[str] = None
    public_phone_number: Optional[str] = None
    business_address_json: Optional[str] = None
    seed: Optional[str] = None
    source_handle: Optional[str] = None
    source_profile_ref: Optional[str] = None
    captured_at: Optional[str] = None


class TargetsResponse(BaseModel):
    targets: List[TargetRow]
    total: int
    limit: int
    offset: int


@router.get("/targets", response_model=TargetsResponse)
async def list_targets(
    workspace_id: str = Query(..., description="Workspace ID"),
    seed: Optional[str] = Query(None, description="Filter by seed handle"),
    source_handle: Optional[str] = Query(
        None, description="Filter by source account handle"
    ),
    search: Optional[str] = Query(None, description="Search handle/name/bio"),
    handle: Optional[str] = Query(
        None, description="Exact handle match (case-insensitive)"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List discovered target accounts from ig_accounts_flat (single source of truth)."""
    from sqlalchemy import text

    try:
        with _get_connection() as conn:
            search_term = (search or "").strip()
            is_search_request = bool(search_term)
            conditions = [
                "a.workspace_id = :wid",
                confirmed_target_condition_sql("a"),
            ]
            params: Dict[str, Any] = {"wid": workspace_id}

            if seed:
                conditions.append("a.seed = :seed")
                params["seed"] = seed

            if source_handle:
                conditions.append("a.source_handle = :src")
                params["src"] = source_handle

            if handle:
                conditions.append("LOWER(a.handle) = LOWER(:handle)")
                params["handle"] = handle

            if is_search_request:
                search_pattern = f"%{search_term}%"
                conditions.append(
                    "(a.handle ILIKE :q OR a.name ILIKE :q OR a.bio ILIKE :q)"
                )
                params["q"] = search_pattern

            where = " AND ".join(conditions)

            total = None
            if should_use_confirmed_targets_total_fast_path(
                seed=seed,
                source_handle=source_handle,
                search=search,
            ):
                total = load_confirmed_targets_total(
                    conn,
                    workspace_id=workspace_id,
                    handle=handle,
                )

            if total is None and not is_search_request:
                total = _safe_count(
                    conn,
                    f"SELECT COUNT(DISTINCT a.handle) FROM ig_accounts_flat a WHERE {where}",
                    params,
                )

            # Fetch page with relevance ordering for search
            params["fetch_lim"] = limit + 1 if is_search_request else limit
            params["off"] = offset

            if is_search_request:
                order_clause = """
                    CASE
                      WHEN handle ILIKE :q THEN 0
                      WHEN name ILIKE :q   THEN 1
                      ELSE 2
                    END ASC, handle ASC
                """
            else:
                order_clause = "handle ASC"

            query_str = f"""
                    SELECT * FROM (
                        SELECT DISTINCT ON (a.handle)
                               a.handle,
                               COALESCE(NULLIF(a.name, ''), r.name) as name,
                               COALESCE(NULLIF(a.bio, ''), r.bio) as bio,
                               COALESCE(NULLIF(a.profile_picture_url, ''), r.profile_picture_url) as profile_picture_url,
                               COALESCE(a.follower_count, r.follower_count) as follower_count,
                               COALESCE(a.following_count, r.following_count) as following_count,
                               COALESCE(a.post_count, r.post_count) as post_count,
                               COALESCE(NULLIF(a.external_url, ''), r.external_url) as external_url,
                               COALESCE(a.is_verified, r.is_verified) as is_verified,
                               COALESCE(a.is_private, r.is_private) as is_private,
                               COALESCE(NULLIF(a.category, ''), r.category) as category,
                               COALESCE(NULLIF(a.public_email, ''), r.public_email) as public_email,
                               COALESCE(NULLIF(a.public_phone_number, ''), r.public_phone_number) as public_phone_number,
                               COALESCE(NULLIF(a.business_address_json, ''), r.business_address_json) as business_address_json,
                               a.seed, a.source_handle, a.source_profile_ref, a.captured_at
                        FROM ig_accounts_flat a
                        LEFT JOIN LATERAL (
                            SELECT name, bio, profile_picture_url,
                                   follower_count, following_count, post_count,
                                   external_url, is_verified, is_private, category,
                                   public_email, public_phone_number, business_address_json
                            FROM ig_accounts_flat r2
                            WHERE r2.workspace_id = a.workspace_id
                              AND r2.handle = a.handle
                              AND (r2.bio IS NOT NULL AND r2.bio != '')
                            ORDER BY r2.updated_at DESC
                            LIMIT 1
                        ) r ON true
                        WHERE {where}
                        ORDER BY a.handle ASC, a.captured_at DESC
                    ) AS deduped
                    ORDER BY {order_clause}
                    LIMIT :fetch_lim OFFSET :off
                """
            
            rows = conn.execute(text(query_str), params).fetchall()
            if is_search_request:
                has_extra = len(rows) > limit
                if has_extra:
                    rows = rows[:limit]
                total = offset + len(rows) + (1 if has_extra else 0)

            targets = [
                TargetRow(
                    handle=r[0],
                    name=r[1],
                    bio=r[2],
                    profile_picture_url=r[3],
                    follower_count=r[4],
                    following_count=r[5],
                    post_count=r[6],
                    external_url=r[7],
                    is_verified=bool(r[8]) if r[8] is not None else None,
                    is_private=bool(r[9]) if r[9] is not None else None,
                    category=r[10],
                    public_email=r[11],
                    public_phone_number=r[12],
                    business_address_json=r[13],
                    seed=r[14],
                    source_handle=r[15],
                    source_profile_ref=r[16],
                    captured_at=str(r[17]) if r[17] else None,
                )
                for r in rows
            ]

            return TargetsResponse(
                targets=targets, total=int(total or 0), limit=limit, offset=offset
            )
    except Exception as e:
        logger.error(f"[IG Insights] Failed to list targets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Profile Tags
# ---------------------------------------------------------------------------


@router.get("/profile-tags", response_model=List[ProfileTagRow])
async def get_profile_tags(
    workspace_id: str = Query(..., description="Workspace ID"),
    seed: Optional[str] = Query(None, description="Filter by seed"),
    handle: Optional[str] = Query(
        None, description="Filter by specific account handle"
    ),
    account_type: Optional[str] = Query(None, description="Filter by account type"),
    influence_tier: Optional[str] = Query(None, description="Filter by influence tier"),
):
    """Query computed profile tags for a given seed or specific handle."""
    from sqlalchemy import text

    if not seed and not handle:
        raise HTTPException(status_code=400, detail="Either seed or handle is required")

    try:
        with _get_connection() as conn:
            if not _table_exists(conn, "ig_account_profiles"):
                return []

            conditions = ["workspace_id = :wid"]
            params: Dict[str, Any] = {"wid": workspace_id}

            if handle:
                conditions.append("account_handle = :handle")
                params["handle"] = handle
            elif seed:
                conditions.append("seed = :seed")
                params["seed"] = seed

            if account_type:
                conditions.append("account_type = :atype")
                params["atype"] = account_type
            if influence_tier:
                conditions.append("influence_tier = :tier")
                params["tier"] = influence_tier

            where = " AND ".join(conditions)
            result = conn.execute(
                text(
                    f"""
                    SELECT id, account_handle, account_type, influence_tier,
                           engagement_potential, follower_following_ratio,
                           bio_keywords_json, bio_detected_locale, computed_at
                    FROM ig_account_profiles
                    WHERE {where}
                    ORDER BY engagement_potential DESC NULLS LAST
                    LIMIT 500
                """
                ),
                params,
            )
            rows = result.fetchall()
            return [
                ProfileTagRow(
                    id=r[0],
                    account_handle=r[1],
                    account_type=r[2],
                    influence_tier=r[3],
                    engagement_potential=r[4],
                    follower_following_ratio=r[5],
                    bio_keywords_json=r[6],
                    bio_detected_locale=r[7],
                    computed_at=str(r[8]) if r[8] else None,
                )
                for r in rows
            ]
    except Exception as e:
        logger.warning(
            f"[IG Insights] profile-tags query failed (schema mismatch?): {e}"
        )
        return []  # Return empty instead of error when schema doesn't match


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------


@router.get("/posts", response_model=List[PostRow])
async def get_posts(
    workspace_id: str = Query(..., description="Workspace ID"),
    seed: Optional[str] = Query(None, description="Filter by seed"),
    handle: Optional[str] = Query(None, description="Filter by specific handle"),
    topic: Optional[str] = Query(None, description="Filter by caption topic"),
    limit: int = Query(100, ge=1, le=500),
):
    """Query analyzed posts for a given seed or specific handle."""
    from sqlalchemy import text

    if not seed and not handle:
        raise HTTPException(status_code=400, detail="Either seed or handle is required")

    try:
        with _get_connection() as conn:
            if not _table_exists(conn, "ig_posts"):
                return []

            params: Dict[str, Any] = {"wid": workspace_id, "lim": limit}
            extra_conditions = []

            if handle:
                extra_conditions.append("p.account_handle = :handle")
                params["handle"] = handle
            if topic:
                extra_conditions.append("p.caption_topic = :topic")
                params["topic"] = topic

            # When querying by handle directly, skip the seed subquery
            if handle and not seed:
                where_parts = ["p.workspace_id = :wid"] + extra_conditions
                where_clause = " AND ".join(where_parts)
                query = f"""
                    SELECT p.id, p.account_handle, p.post_shortcode, p.post_type,
                           p.post_url, p.thumbnail_url, p.like_count, p.comment_count,
                           p.caption, p.hashtags_json, p.caption_topic,
                           p.caption_sentiment, p.posted_at, p.captured_at
                    FROM ig_posts p
                    WHERE {where_clause}
                    ORDER BY p.captured_at DESC
                    LIMIT :lim
                """
            else:
                params["seed"] = seed
                extra_where = (
                    (" AND " + " AND ".join(extra_conditions))
                    if extra_conditions
                    else ""
                )
                query = f"""
                    SELECT p.id, p.account_handle, p.post_shortcode, p.post_type,
                           p.post_url, p.thumbnail_url, p.like_count, p.comment_count,
                           p.caption, p.hashtags_json, p.caption_topic,
                           p.caption_sentiment, p.posted_at, p.captured_at
                    FROM ig_posts p
                    WHERE p.workspace_id = :wid
                      AND p.account_handle IN (
                          SELECT handle FROM ig_accounts_flat
                          WHERE workspace_id = :wid
                            AND seed = :seed
                            AND {confirmed_target_condition_sql()}
                      ){extra_where}
                    ORDER BY p.captured_at DESC
                    LIMIT :lim
                """

            result = conn.execute(text(query), params)
            rows = result.fetchall()
            return [
                PostRow(
                    id=r[0],
                    account_handle=r[1],
                    post_shortcode=r[2],
                    post_type=r[3],
                    post_url=r[4],
                    thumbnail_url=r[5],
                    like_count=r[6],
                    comment_count=r[7],
                    caption=r[8],
                    hashtags_json=r[9],
                    caption_topic=r[10],
                    caption_sentiment=r[11],
                    posted_at=str(r[12]) if r[12] else None,
                    captured_at=str(r[13]) if r[13] else None,
                )
                for r in rows
            ]
    except Exception as e:
        logger.warning(f"[IG Insights] posts query failed (schema mismatch?): {e}")
        return []  # Return empty instead of error when schema doesn't match


@router.get("/latest-batch-pin-summary", response_model=LatestBatchPinSummaryResponse)
async def get_latest_batch_pin_summary(
    workspace_id: str = Query(..., description="Workspace ID"),
    handle: str = Query(..., description="Target handle"),
):
    """Return the latest batch-pin attempt and the latest completed result for one handle."""
    from sqlalchemy import text

    normalized_handle = _normalize_ig_handle(handle)
    if not normalized_handle:
        raise HTTPException(status_code=400, detail="handle is required")

    base_query = """
        SELECT id, execution_id, status, created_at, completed_at, execution_context
        FROM tasks
        WHERE workspace_id = :wid
          AND pack_id = 'ig_batch_pin_references'
          AND lower(
                coalesce(
                    execution_context->'inputs'->>'target_handle',
                    execution_context->'inputs'->>'target_username',
                    ''
                )
              ) = :handle
        ORDER BY created_at DESC
        LIMIT 1
    """
    completed_query = """
        SELECT id, execution_id, status, created_at, completed_at, execution_context
        FROM tasks
        WHERE workspace_id = :wid
          AND pack_id = 'ig_batch_pin_references'
          AND lower(
                coalesce(
                    execution_context->'inputs'->>'target_handle',
                    execution_context->'inputs'->>'target_username',
                    ''
                )
              ) = :handle
          AND execution_context->'workflow_result' IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 1
    """

    try:
        with _get_connection() as conn:
            latest_attempt_row = conn.execute(
                text(base_query), {"wid": workspace_id, "handle": normalized_handle}
            ).fetchone()
            latest_completed_row = conn.execute(
                text(completed_query), {"wid": workspace_id, "handle": normalized_handle}
            ).fetchone()

        return LatestBatchPinSummaryResponse(
            latest_attempt=_build_batch_pin_execution_summary(latest_attempt_row),
            latest_completed=_build_batch_pin_execution_summary(latest_completed_row),
        )
    except Exception as e:
        logger.warning(f"[IG Insights] latest batch pin summary query failed: {e}")
        return LatestBatchPinSummaryResponse()


@router.get("/pin-failed-attempts", response_model=PinFailedAttemptListResponse)
async def get_pin_failed_attempts(
    workspace_id: str = Query(..., description="Workspace ID"),
    handle: Optional[str] = Query(None, description="Optional source handle"),
    status: Optional[str] = Query(None, description="Optional failed attempt status"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of failed pin attempts to include"),
    offset: int = Query(0, ge=0, description="Failed attempt offset"),
):
    from capabilities.ig.services.pin_failed_attempt_store import PostgresIGPinFailedAttemptStore

    try:
        store = PostgresIGPinFailedAttemptStore()
        rows, total = store.list_attempts(
            workspace_id=workspace_id,
            source_handle=handle,
            status=status,
            limit=limit,
            offset=offset,
        )
        return PinFailedAttemptListResponse(
            attempts=[_build_pin_failed_attempt_row(row) for row in rows],
            total=total,
        )
    except Exception as e:
        logger.warning(f"[IG Insights] pin failed attempts query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to load pin failed attempts")


@router.post("/pin-failed-attempts/retry", response_model=RetryPinFailedAttemptsResponse)
async def retry_pin_failed_attempts(
    payload: RetryPinFailedAttemptsRequest,
    workspace_id: str = Query(..., description="Workspace ID"),
):
    from capabilities.ig.services.pin_failed_attempt_store import PostgresIGPinFailedAttemptStore
    from capabilities.ig.tools.ig_pin_reference import ig_pin_reference

    store = PostgresIGPinFailedAttemptStore()
    attempts = store.list_retry_candidates(
        workspace_id=workspace_id,
        source_handle=payload.handle,
        dedupe_keys=payload.dedupe_keys,
        limit=payload.limit,
    )

    results: List[RetryPinFailedAttemptsResult] = []
    recovered = 0
    still_failed = 0

    for attempt in attempts:
        image_url = str(attempt.get("image_url") or "").strip()
        source_handle = str(attempt.get("source_handle") or "").strip()
        source_shortcode = str(attempt.get("source_shortcode") or "").strip()
        source_url = str(attempt.get("source_url") or "").strip()

        if not image_url:
            still_failed += 1
            results.append(
                RetryPinFailedAttemptsResult(
                    dedupe_key=str(attempt.get("dedupe_key") or ""),
                    source_shortcode=source_shortcode or None,
                    status="error",
                    final_disposition="skipped_no_reference",
                    error_kind="missing_image_url",
                    error="Retry skipped because image_url is missing",
                )
            )
            continue

        retry_result = await ig_pin_reference(
            workspace_id=workspace_id,
            image_url=image_url,
            source_handle=source_handle,
            source_shortcode=source_shortcode,
            source_url=source_url,
            pinned_by=payload.pinned_by or "retry_failed_pins_api",
            trigger=str(attempt.get("trigger") or "retry_failed_pin"),
            parent_execution_id=attempt.get("parent_execution_id"),
        )
        retry_status = str(retry_result.get("status") or "")
        final_disposition = retry_result.get("final_disposition")
        if retry_status in {"pinned", "duplicate"}:
            recovered += 1
        else:
            still_failed += 1
        results.append(
            RetryPinFailedAttemptsResult(
                dedupe_key=str(attempt.get("dedupe_key") or ""),
                source_shortcode=source_shortcode or None,
                status=retry_status,
                final_disposition=str(final_disposition) if final_disposition else None,
                reference_id=retry_result.get("reference_id"),
                error_kind=retry_result.get("error_kind"),
                error=retry_result.get("error"),
            )
        )

    return RetryPinFailedAttemptsResponse(
        retried=len(attempts),
        recovered=recovered,
        still_failed=still_failed,
        results=results,
    )


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


@router.get("/network", response_model=List[NetworkOverlap])
async def get_network(
    workspace_id: str = Query(..., description="Workspace ID"),
    seeds: str = Query(..., description="Comma-separated seed handles"),
    min_overlap: int = Query(2, ge=2, description="Minimum overlap count"),
):
    """Find accounts followed by multiple seeds (common following)."""
    from sqlalchemy import text

    try:
        seed_list = [s.strip() for s in seeds.split(",") if s.strip()]
        if len(seed_list) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 seeds")

        with _get_connection() as conn:
            if not _table_exists(conn, "ig_follow_edges"):
                return []

            # Use ANY for parameterised IN
            result = conn.execute(
                text(
                    """
                    SELECT target_handle,
                           COUNT(DISTINCT source_handle) as overlap_count,
                           ARRAY_AGG(DISTINCT source_handle) as shared_by
                    FROM ig_follow_edges
                    WHERE workspace_id = :wid
                      AND source_handle = ANY(:seeds)
                    GROUP BY target_handle
                    HAVING COUNT(DISTINCT source_handle) >= :min_ov
                    ORDER BY overlap_count DESC
                    LIMIT 200
                """
                ),
                {"wid": workspace_id, "seeds": seed_list, "min_ov": min_overlap},
            )
            rows = result.fetchall()
            return [
                NetworkOverlap(
                    target_handle=r[0],
                    overlap_count=r[1],
                    shared_by=list(r[2]) if r[2] else [],
                )
                for r in rows
            ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[IG Insights] network query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------


@router.get("/personas", response_model=List[PersonaRow])
async def get_personas(
    workspace_id: str = Query(..., description="Workspace ID"),
    seed: Optional[str] = Query(None, description="Filter by seed"),
    handles: Optional[str] = Query(None, description="Comma-separated handles"),
):
    """Query generated personas."""
    from sqlalchemy import text

    try:
        with _get_connection() as conn:
            if not _table_exists(conn, "ig_generated_personas"):
                return []

            conditions = ["gp.workspace_id = :wid"]
            params: Dict[str, Any] = {"wid": workspace_id}

            if seed:
                conditions.append(
                    f"""
                    gp.account_handle IN (
                        SELECT handle FROM ig_accounts_flat
                        WHERE workspace_id = :wid
                          AND seed = :seed
                          AND {confirmed_target_condition_sql()}
                    )
                """
                )
                params["seed"] = seed

            if handles:
                handle_list = [h.strip() for h in handles.split(",") if h.strip()]
                conditions.append("gp.account_handle = ANY(:handles)")
                params["handles"] = handle_list

            where = " AND ".join(conditions)
            result = conn.execute(
                text(
                    f"""
                    SELECT gp.id, gp.account_handle, gp.persona_summary,
                           gp.persona_locale, gp.key_traits_json,
                           gp.content_themes_json, gp.demographics_json,
                           gp.collaboration_potential, gp.recommended_approach,
                           gp.generated_at
                    FROM ig_generated_personas gp
                    WHERE {where}
                    ORDER BY gp.generated_at DESC
                    LIMIT 100
                """
                ),
                params,
            )
            rows = result.fetchall()
            return [
                PersonaRow(
                    id=r[0],
                    account_handle=r[1],
                    persona_summary=r[2],
                    persona_locale=r[3],
                    key_traits_json=r[4],
                    content_themes_json=r[5],
                    demographics_json=r[6],
                    collaboration_potential=r[7],
                    recommended_approach=r[8],
                    generated_at=str(r[9]) if r[9] else None,
                )
                for r in rows
            ]
    except Exception as e:
        logger.warning(f"[IG Insights] personas query failed (schema mismatch?): {e}")
        return []  # Return empty instead of error when schema doesn't match


# ---------------------------------------------------------------------------
# Seed Status (single seed detail)
# ---------------------------------------------------------------------------


@router.get("/seed-status")
async def get_seed_status(
    workspace_id: str = Query(..., description="Workspace ID"),
    seed: str = Query(..., description="Seed handle"),
):
    """Get detailed analysis status for a single seed."""
    from sqlalchemy import text

    try:
        with _get_connection() as conn:
            status: Dict[str, Any] = {"seed": seed, "workspace_id": workspace_id}

            # Targets count (all accounts from scroll)
            r = conn.execute(
                text(
                    "SELECT COUNT(*) FROM ig_accounts_flat "
                    "WHERE workspace_id = :wid AND seed = :s "
                    "AND handle NOT LIKE '__seed_placeholder__%'"
                ),
                {"wid": workspace_id, "s": seed},
            ).fetchone()
            status["target_count"] = r[0] if r else 0

            # Visited count (accounts with actual page visit data)
            # Use follower_count IS NOT NULL — every successful page visit extracts follower count.
            # Cannot use bio because many IG accounts have no bio text.
            r = conn.execute(
                text(
                    "SELECT COUNT(*) FROM ig_accounts_flat "
                    "WHERE workspace_id = :wid AND seed = :s AND follower_count IS NOT NULL"
                ),
                {"wid": workspace_id, "s": seed},
            ).fetchone()
            status["visited_count"] = r[0] if r else 0

            # Tags count
            if _table_exists(conn, "ig_account_profiles"):
                r = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM ig_account_profiles WHERE workspace_id = :wid AND seed = :s"
                    ),
                    {"wid": workspace_id, "s": seed},
                ).fetchone()
                status["tags_count"] = r[0] if r else 0
            else:
                status["tags_count"] = 0

            # Posts count - ig_posts may not have seed column, use JOIN
            if _table_exists(conn, "ig_posts"):
                if _column_exists(conn, "ig_posts", "seed"):
                    r = conn.execute(
                        text(
                            "SELECT COUNT(*) FROM ig_posts WHERE workspace_id = :wid AND seed = :s"
                        ),
                        {"wid": workspace_id, "s": seed},
                    ).fetchone()
                    status["posts_count"] = r[0] if r else 0
                else:
                    # Fallback: count posts by handles that belong to this seed
                    r = conn.execute(
                        text(
                            """SELECT COUNT(*) FROM ig_posts p
                               WHERE p.workspace_id = :wid AND p.account_handle IN (
                                   SELECT handle FROM ig_accounts_flat
                                   WHERE workspace_id = :wid
                                     AND seed = :s
                                     AND """
                            + confirmed_target_condition_sql()
                            + """
                               )"""
                        ),
                        {"wid": workspace_id, "s": seed},
                    ).fetchone()
                    status["posts_count"] = r[0] if r else 0
            else:
                status["posts_count"] = 0

            # Edges count
            if _table_exists(conn, "ig_follow_edges"):
                r = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM ig_follow_edges WHERE workspace_id = :wid AND discovered_via_seed = :s"
                    ),
                    {"wid": workspace_id, "s": seed},
                ).fetchone()
                status["edges_count"] = r[0] if r else 0
            else:
                status["edges_count"] = 0

            # Personas count
            if _table_exists(conn, "ig_generated_personas"):
                r = conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM ig_generated_personas
                        WHERE workspace_id = :wid AND account_handle IN (
                            SELECT handle FROM ig_accounts_flat
                            WHERE workspace_id = :wid
                              AND seed = :s
                              AND """
                        + confirmed_target_condition_sql()
                        + """
                        )
                    """
                    ),
                    {"wid": workspace_id, "s": seed},
                ).fetchone()
                status["personas_count"] = r[0] if r else 0
            else:
                status["personas_count"] = 0

            return status

    except Exception as e:
        logger.error(f"[IG Insights] seed-status query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
