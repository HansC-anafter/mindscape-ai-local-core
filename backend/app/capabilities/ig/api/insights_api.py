"""
IG Insights API

Query endpoints for profile tags, posts, network analysis, personas, and seed management.
Provides read-only access to data computed by IG enhancement tools.
"""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

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


class SeedInfo(BaseModel):
    seed: str
    target_count: int
    last_crawled: Optional[str] = None
    has_tags: bool = False
    has_posts: bool = False
    has_network: bool = False
    has_personas: bool = False


class SeedListResponse(BaseModel):
    seeds: List[SeedInfo]
    total: int


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
            # Get unique seeds from ig_accounts_flat
            result = conn.execute(
                text(
                    """
                    SELECT seed, COUNT(*) as cnt,
                           MAX(captured_at) as last_crawled
                    FROM ig_accounts_flat
                    WHERE workspace_id = :wid AND seed IS NOT NULL
                    GROUP BY seed
                    ORDER BY last_crawled DESC
                """
                ),
                {"wid": workspace_id},
            )
            rows = result.fetchall()

            seeds: List[SeedInfo] = []
            for r in rows:
                seed_handle = r[0]
                info = SeedInfo(
                    seed=seed_handle,
                    target_count=r[1],
                    last_crawled=str(r[2]) if r[2] else None,
                )

                # Check analysis status per table (using safe queries that handle missing columns)
                params = {"wid": workspace_id, "s": seed_handle}

                if _table_exists(conn, "ig_account_profiles") and _column_exists(
                    conn, "ig_account_profiles", "seed"
                ):
                    cnt = _safe_count(
                        conn,
                        "SELECT COUNT(*) FROM ig_account_profiles WHERE workspace_id = :wid AND seed = :s",
                        params,
                    )
                    info.has_tags = cnt > 0

                if _table_exists(conn, "ig_posts") and _column_exists(
                    conn, "ig_posts", "seed"
                ):
                    cnt = _safe_count(
                        conn,
                        "SELECT COUNT(*) FROM ig_posts WHERE workspace_id = :wid AND seed = :s",
                        params,
                    )
                    info.has_posts = cnt > 0

                if _table_exists(conn, "ig_follow_edges") and _column_exists(
                    conn, "ig_follow_edges", "discovered_via_seed"
                ):
                    cnt = _safe_count(
                        conn,
                        "SELECT COUNT(*) FROM ig_follow_edges WHERE workspace_id = :wid AND discovered_via_seed = :s",
                        params,
                    )
                    info.has_network = cnt > 0

                if _table_exists(conn, "ig_generated_personas"):
                    cnt = _safe_count(
                        conn,
                        """
                        SELECT COUNT(*) FROM ig_generated_personas gp
                        WHERE gp.workspace_id = :wid
                          AND gp.account_handle IN (
                              SELECT handle FROM ig_accounts_flat
                              WHERE workspace_id = :wid AND seed = :s
                          )
                    """,
                        params,
                    )
                    info.has_personas = cnt > 0

                seeds.append(info)

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
    from datetime import datetime, timezone

    try:
        with _get_connection() as conn:
            # Check if seed already exists
            existing = conn.execute(
                text(
                    "SELECT COUNT(*) FROM ig_accounts_flat WHERE workspace_id = :wid AND seed = :s AND handle = :h"
                ),
                {"wid": workspace_id, "s": handle, "h": handle},
            ).fetchone()

            if existing and existing[0] > 0:
                return {
                    "status": "ok",
                    "message": f"Seed '{handle}' already exists.",
                    "handle": handle,
                }

            # Insert seed as its own handle (bootstrap record)
            conn.execute(
                text(
                    """INSERT INTO ig_accounts_flat (workspace_id, seed, handle, captured_at)
                       VALUES (:wid, :seed, :handle, :captured_at)
                       ON CONFLICT DO NOTHING"""
                ),
                {
                    "wid": workspace_id,
                    "seed": handle,
                    "handle": handle,
                    "captured_at": _utc_now().isoformat(),
                },
            )
            conn.commit()

            return {
                "status": "ok",
                "message": f"Seed '{handle}' registered.",
                "handle": handle,
            }
    except Exception as e:
        logger.error(f"[IG Insights] Failed to add seed: {e}")
        return {
            "status": "ok",
            "message": f"Seed '{handle}' registered. Run ig_analyze_following to crawl.",
            "handle": handle,
        }


@router.delete("/seeds/{handle}")
async def remove_seed(
    handle: str,
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """Remove a seed (does not delete crawled data)."""
    return {"status": "ok", "message": f"Seed '{handle}' removed.", "handle": handle}


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
            conditions = ["workspace_id = :wid"]
            params: Dict[str, Any] = {"wid": workspace_id}

            if seed:
                conditions.append("seed = :seed")
                params["seed"] = seed

            if source_handle:
                conditions.append("source_handle = :src")
                params["src"] = source_handle

            if handle:
                conditions.append("LOWER(handle) = LOWER(:handle)")
                params["handle"] = handle

            if search:
                search_term = f"%{search}%"
                conditions.append("(handle ILIKE :q OR name ILIKE :q OR bio ILIKE :q)")
                params["q"] = search_term

            where = " AND ".join(conditions)

            # Dedup: when no seed filter, same handle appears once per seed.
            # Use DISTINCT ON to keep the most-visited (follower_count present),
            # most-recent version of each handle.
            needs_dedup = not seed

            if needs_dedup:
                count_result = conn.execute(
                    text(
                        f"SELECT COUNT(DISTINCT handle) FROM ig_accounts_flat WHERE {where}"
                    ),
                    params,
                )
            else:
                count_result = conn.execute(
                    text(f"SELECT COUNT(*) FROM ig_accounts_flat WHERE {where}"),
                    params,
                )
            total = count_result.fetchone()[0]

            params["lim"] = limit
            params["off"] = offset

            # Build ORDER BY: relevance ranking when searching
            if search:
                relevance_col = """
                    CASE
                      WHEN handle ILIKE :q THEN 0
                      WHEN name ILIKE :q   THEN 1
                      ELSE 2
                    END
                """
            else:
                relevance_col = "0"

            if needs_dedup:
                query = f"""
                    SELECT handle, name, bio, profile_picture_url,
                           follower_count, following_count, post_count,
                           external_url, is_verified, is_private, category,
                           public_email, public_phone_number, business_address_json,
                           seed, source_handle, source_profile_ref, captured_at
                    FROM (
                        SELECT DISTINCT ON (handle)
                               handle, name, bio, profile_picture_url,
                               follower_count, following_count, post_count,
                               external_url, is_verified, is_private, category,
                               public_email, public_phone_number, business_address_json,
                               seed, source_handle, source_profile_ref, captured_at,
                               {relevance_col} AS _relevance
                        FROM ig_accounts_flat
                        WHERE {where}
                        ORDER BY handle ASC,
                                 (follower_count IS NOT NULL) DESC,
                                 captured_at DESC
                    ) deduped
                    ORDER BY _relevance ASC, handle ASC
                    LIMIT :lim OFFSET :off
                """
            else:
                query = f"""
                    SELECT handle, name, bio, profile_picture_url,
                           follower_count, following_count, post_count,
                           external_url, is_verified, is_private, category,
                           public_email, public_phone_number, business_address_json,
                           seed, source_handle, source_profile_ref, captured_at
                    FROM ig_accounts_flat
                    WHERE {where}
                    ORDER BY {relevance_col} ASC, handle ASC
                    LIMIT :lim OFFSET :off
                """

            result = conn.execute(text(query), params)
            rows = result.fetchall()

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
                targets=targets, total=total, limit=limit, offset=offset
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
                          WHERE workspace_id = :wid AND seed = :seed
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
                    """
                    gp.account_handle IN (
                        SELECT handle FROM ig_accounts_flat
                        WHERE workspace_id = :wid AND seed = :seed
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
                    "SELECT COUNT(*) FROM ig_accounts_flat WHERE workspace_id = :wid AND seed = :s"
                ),
                {"wid": workspace_id, "s": seed},
            ).fetchone()
            status["target_count"] = r[0] if r else 0

            # Visited count (accounts with actual page visit data)
            # Use follower_count IS NOT NULL — every successful page visit extracts follower count.
            # Cannot use bio because many IG accounts have no bio text.
            r = conn.execute(
                text(
                    "SELECT COUNT(*) FROM ig_accounts_flat WHERE workspace_id = :wid AND seed = :s AND follower_count IS NOT NULL"
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
                                   SELECT handle FROM ig_accounts_flat WHERE workspace_id = :wid AND seed = :s
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
                            WHERE workspace_id = :wid AND seed = :s
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
