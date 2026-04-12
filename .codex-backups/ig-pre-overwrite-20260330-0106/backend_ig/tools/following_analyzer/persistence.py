"""
Database persistence functions for Instagram following analyzer.

This module handles persisting account data and follow edges to PostgreSQL.
"""

import json
import logging
import traceback
import uuid
from typing import Any, Dict, List, Optional

from capabilities.ig.services.confirmed_targets import (
    is_confirmed_target_source_context,
    upsert_confirmed_target_handles,
)

logger = logging.getLogger(__name__)


def _get_db_engine():
    """
    Get SQLAlchemy engine with fallback import paths.
    """
    from sqlalchemy import create_engine

    try:
        from app.database.config import get_postgres_url_core

        return create_engine(get_postgres_url_core())
    except ImportError:
        from backend.app.core.database import get_db_engine

        return get_db_engine()


def _to_int(value: Any) -> Optional[int]:
    """Convert value to int, returning None on failure."""
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        return int(value)
    except Exception:
        return None


def _to_bool(value: Any) -> Optional[bool]:
    """Convert value to bool, returning None for non-boolean values."""
    if value is True:
        return True
    if value is False:
        return False
    return None


def _parse_count_text(text: Any) -> Optional[int]:
    """Parse count text like '2.4萬', '1.2K', '451 followers' to int."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    s = str(text).strip().lower()
    # Remove common suffixes
    for suffix in ["followers", "following", "posts", " "]:
        s = s.replace(suffix, "")
    s = s.strip()
    if not s:
        return None
    try:
        # Handle K/M/萬/万 multipliers
        multiplier = 1
        if s.endswith("k"):
            multiplier = 1000
            s = s[:-1]
        elif s.endswith("m"):
            multiplier = 1000000
            s = s[:-1]
        elif s.endswith("萬") or s.endswith("万"):
            multiplier = 10000
            s = s[:-1]
        # Remove commas
        s = s.replace(",", "")
        return int(float(s) * multiplier)
    except Exception:
        return None


def load_accounts_from_db(
    workspace_id: str,
    seed: str,
    source_profile_ref: Optional[str] = None,
    include_unverified: bool = False,
) -> List[Dict[str, Any]]:
    """
    Load accounts from ig_accounts_flat table for a given workspace/seed.

    This is used as a fallback when artifact content is empty but
    accounts have been persisted incrementally during scrolling.

    Args:
        workspace_id: Workspace ID
        seed: Target username (seed)
        source_profile_ref: Optional browser profile reference for filtering

    Returns:
        List of account dicts with normalized keys
    """
    if not workspace_id or not seed:
        return []

    try:
        engine = _get_db_engine()
    except ImportError as e:
        logger.warning(f"[IGFollowingAnalyzer] Failed to import database module: {e}")
        return []

    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            # Build query with optional source_profile_ref filter
            if source_profile_ref:
                # Normalize trailing slashes for comparison
                normalized_ref = source_profile_ref.rstrip("/")
                _sc_filter = (
                    "AND source_context = 'following_list'"
                    if not include_unverified
                    else "AND source_context IN ('following_list', 'unknown')"
                )
                stmt = text(
                    f"""
                    SELECT handle, name, is_verified, follower_count, following_count,
                           post_count, bio, external_url, profile_picture_url, category,
                           tags_json, captured_at
                    FROM ig_accounts_flat
                    WHERE workspace_id = :workspace_id
                      AND seed = :seed
                      AND RTRIM(COALESCE(source_profile_ref, ''), '/') = :source_profile_ref
                      AND handle NOT LIKE '__seed_placeholder__%'
                      {_sc_filter}
                    ORDER BY captured_at DESC
                """
                )
                result = conn.execute(
                    stmt,
                    {
                        "workspace_id": workspace_id,
                        "seed": seed,
                        "source_profile_ref": normalized_ref,
                    },
                )
            else:
                _sc_filter = (
                    "AND source_context = 'following_list'"
                    if not include_unverified
                    else "AND source_context IN ('following_list', 'unknown')"
                )
                stmt = text(
                    f"""
                    SELECT handle, name, is_verified, follower_count, following_count,
                           post_count, bio, external_url, profile_picture_url, category,
                           tags_json, captured_at
                    FROM ig_accounts_flat
                    WHERE workspace_id = :workspace_id
                      AND seed = :seed
                      AND handle NOT LIKE '__seed_placeholder__%'
                      {_sc_filter}
                    ORDER BY captured_at DESC
                """
                )
                result = conn.execute(
                    stmt,
                    {
                        "workspace_id": workspace_id,
                        "seed": seed,
                    },
                )

            accounts = []
            seen_handles = set()
            for row in result:
                handle = row.handle
                if not handle or handle in seen_handles:
                    continue
                seen_handles.add(handle)

                # Parse tags_json if present
                tags = None
                if row.tags_json:
                    try:
                        tags = json.loads(row.tags_json)
                    except Exception:
                        pass

                accounts.append(
                    {
                        "handle": handle,
                        "username": handle,
                        "name": row.name,
                        "full_name": row.name,
                        "is_verified": row.is_verified,
                        "follower_count": row.follower_count,
                        "following_count": row.following_count,
                        "post_count": row.post_count,
                        "bio": row.bio,
                        "external_url": row.external_url,
                        "profile_picture_url": row.profile_picture_url,
                        "category": row.category,
                        "tags": tags,
                        "captured_at": (
                            str(row.captured_at) if row.captured_at else None
                        ),
                    }
                )

            logger.info(
                f"[IGFollowingAnalyzer] Loaded {len(accounts)} accounts from ig_accounts_flat "
                f"for workspace={workspace_id}, seed={seed}"
            )
            return accounts

    except Exception as e:
        logger.warning(
            f"[IGFollowingAnalyzer] Failed to load accounts from ig_accounts_flat: {e}"
        )
        return []


def get_saved_count(workspace_id: str, seed: str) -> int:
    """
    Return the number of unique accounts persisted in ig_accounts_flat
    for a given workspace/seed.  Lightweight count-only query used by
    the scroll loop to decide whether to stop early.

    Seed placeholder rows are excluded because they do not represent
    real following-list accounts and would otherwise create off-by-one
    false positives against expected_following_count.
    """
    if not workspace_id or not seed:
        return 0
    try:
        engine = _get_db_engine()
        from sqlalchemy import text

        with engine.connect() as conn:
            r = conn.execute(
                text(
                    "SELECT COUNT(*) FROM ig_accounts_flat "
                    "WHERE workspace_id = :wid AND seed = :seed "
                    "AND handle NOT LIKE '__seed_placeholder__%'"
                ),
                {"wid": workspace_id, "seed": seed},
            ).fetchone()
            return r[0] if r else 0
    except Exception as e:
        logger.warning(f"[IGFollowingAnalyzer] get_saved_count failed: {e}")
        return 0


def persist_accounts_flat(
    workspace_id: str,
    seed: str,
    source_account_handle: Optional[str],
    source_profile_ref: Optional[str],
    accounts: List[Dict[str, Any]],
    analyzed_at: str,
    execution_id: Optional[str],
    trace_id: Optional[str],
    artifact_id: Optional[str],
    schema_version: Optional[str],
    seed_version: Optional[str],
    capture_method: Optional[str],
    run_mode: Optional[str],
    source_context: Optional[str] = None,
) -> None:
    """
    Persist account snapshots to PostgreSQL ig_accounts_flat table.

    Uses UPSERT pattern (INSERT ... ON CONFLICT DO UPDATE) to enable
    incremental writes during scrolling without duplicates.
    """
    if not workspace_id or not seed or not accounts:
        return

    rows: List[tuple] = []
    confirmed_target_handles = set()
    for account in accounts:
        if not isinstance(account, dict):
            continue
        handle = (account.get("username") or account.get("handle") or "").strip()
        if not handle:
            continue
        captured_at = (
            account.get("fetched_at")
            or account.get("page_analyzed_at")
            or account.get("captured_at")
            or analyzed_at
        )
        tags = account.get("tags")
        tags_json = (
            json.dumps(tags, ensure_ascii=False)
            if isinstance(tags, (list, dict))
            else None
        )

        grid_posts = account.get("grid_posts_json") or account.get("grid_posts")
        grid_posts_json = None
        if grid_posts:
            grid_posts_json = (
                grid_posts
                if isinstance(grid_posts, str)
                else json.dumps(grid_posts, ensure_ascii=False)
            )

        vision_analysis = account.get("vision_analysis_json") or account.get(
            "vision_analysis"
        )
        vision_analysis_json = None
        if vision_analysis:
            vision_analysis_json = (
                vision_analysis
                if isinstance(vision_analysis, str)
                else json.dumps(vision_analysis, ensure_ascii=False)
            )

        # Determine source_context per account (from _source_context tag or function param)
        account_source = account.get("_source_context") or source_context or "unknown"
        if is_confirmed_target_source_context(account_source):
            confirmed_target_handles.add(handle)
        rows.append(
            (
                str(uuid.uuid4()),
                workspace_id,
                seed,
                source_account_handle,
                source_profile_ref,
                handle,
                account.get("name")
                or account.get("full_name")
                or account.get("display_name"),
                _to_bool(account.get("is_verified") or account.get("verified")),
                _to_bool(account.get("is_private")),
                _to_int(account.get("follower_count") or account.get("followers"))
                or _parse_count_text(account.get("follower_count_text")),
                _to_int(account.get("following_count") or account.get("following"))
                or _parse_count_text(account.get("following_count_text")),
                _to_int(account.get("post_count") or account.get("posts"))
                or _parse_count_text(account.get("post_count_text")),
                account.get("bio")
                or account.get("biography")
                or account.get("profile_bio"),
                account.get("external_url") or account.get("account_link"),
                account.get("profile_picture_url")
                or account.get("profile_image_url")
                or account.get("profile_pic_url")
                or account.get("avatar_url"),
                account.get("category"),
                tags_json,
                grid_posts_json,
                vision_analysis_json,
                account.get("public_email"),
                account.get("public_phone_number"),
                account.get("business_address_json"),
                str(captured_at),
                execution_id,
                trace_id,
                artifact_id,
                schema_version,
                seed_version,
                capture_method,
                run_mode,
                account_source,
            )
        )

    if not rows:
        return

    try:
        engine = _get_db_engine()
    except ImportError as e:
        logger.warning(f"[IGFollowingAnalyzer] Failed to import database module: {e}")
        return

    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            # Use UPSERT pattern: INSERT ... ON CONFLICT DO UPDATE
            # This enables incremental writes during scrolling without duplicates
            stmt = text(
                """
                INSERT INTO ig_accounts_flat (
                    id, workspace_id, seed, source_handle, source_profile_ref,
                    handle, name, is_verified, is_private, follower_count, following_count, post_count,
                    bio, external_url, profile_picture_url, category, tags_json,
                    grid_posts_json, vision_analysis_json,
                    public_email, public_phone_number, business_address_json,
                    captured_at, execution_id, trace_id, artifact_id,
                    schema_version, seed_version, capture_method, run_mode,
                    source_context
                ) VALUES (
                    :id, :workspace_id, :seed, :source_handle, :source_profile_ref,
                    :handle, :name, :is_verified, :is_private, :follower_count, :following_count, :post_count,
                    :bio, :external_url, :profile_picture_url, :category, :tags_json,
                    :grid_posts_json, :vision_analysis_json,
                    :public_email, :public_phone_number, :business_address_json,
                    :captured_at, :execution_id, :trace_id, :artifact_id,
                    :schema_version, :seed_version, :capture_method, :run_mode,
                    :source_context
                )
                ON CONFLICT (workspace_id, seed, handle) DO UPDATE SET
                    source_handle = COALESCE(EXCLUDED.source_handle, ig_accounts_flat.source_handle),
                    source_profile_ref = COALESCE(EXCLUDED.source_profile_ref, ig_accounts_flat.source_profile_ref),
                    name = COALESCE(NULLIF(EXCLUDED.name, ''), ig_accounts_flat.name),
                    is_verified = COALESCE(EXCLUDED.is_verified, ig_accounts_flat.is_verified),
                    is_private = COALESCE(EXCLUDED.is_private, ig_accounts_flat.is_private),
                    follower_count = COALESCE(EXCLUDED.follower_count, ig_accounts_flat.follower_count),
                    following_count = COALESCE(EXCLUDED.following_count, ig_accounts_flat.following_count),
                    post_count = COALESCE(EXCLUDED.post_count, ig_accounts_flat.post_count),
                    bio = COALESCE(NULLIF(EXCLUDED.bio, ''), ig_accounts_flat.bio),
                    external_url = COALESCE(NULLIF(EXCLUDED.external_url, ''), ig_accounts_flat.external_url),
                    profile_picture_url = COALESCE(NULLIF(EXCLUDED.profile_picture_url, ''), ig_accounts_flat.profile_picture_url),
                    category = COALESCE(NULLIF(EXCLUDED.category, ''), ig_accounts_flat.category),
                    tags_json = COALESCE(NULLIF(EXCLUDED.tags_json, ''), ig_accounts_flat.tags_json),
                    grid_posts_json = COALESCE(NULLIF(EXCLUDED.grid_posts_json, ''), ig_accounts_flat.grid_posts_json),
                    vision_analysis_json = COALESCE(NULLIF(EXCLUDED.vision_analysis_json, ''), ig_accounts_flat.vision_analysis_json),
                    public_email = COALESCE(NULLIF(EXCLUDED.public_email, ''), ig_accounts_flat.public_email),
                    public_phone_number = COALESCE(NULLIF(EXCLUDED.public_phone_number, ''), ig_accounts_flat.public_phone_number),
                    business_address_json = COALESCE(NULLIF(EXCLUDED.business_address_json, ''), ig_accounts_flat.business_address_json),
                    captured_at = EXCLUDED.captured_at,
                    execution_id = EXCLUDED.execution_id,
                    trace_id = EXCLUDED.trace_id,
                    artifact_id = EXCLUDED.artifact_id,
                    run_mode = EXCLUDED.run_mode,
                    source_context = CASE
                        WHEN EXCLUDED.source_context = 'following_list' THEN 'following_list'
                        WHEN ig_accounts_flat.source_context = 'following_list' THEN ig_accounts_flat.source_context
                        WHEN EXCLUDED.source_context = 'suggestion' THEN 'suggestion'
                        WHEN ig_accounts_flat.source_context = 'suggestion' THEN ig_accounts_flat.source_context
                        ELSE COALESCE(EXCLUDED.source_context, ig_accounts_flat.source_context, 'unknown')
                    END,
                    updated_at = NOW()
            """
            )
            for row in rows:
                conn.execute(
                    stmt,
                    {
                        "id": row[0],
                        "workspace_id": row[1],
                        "seed": row[2],
                        "source_handle": row[3],
                        "source_profile_ref": row[4],
                        "handle": row[5],
                        "name": row[6],
                        "is_verified": row[7],
                        "is_private": row[8],
                        "follower_count": row[9],
                        "following_count": row[10],
                        "post_count": row[11],
                        "bio": row[12],
                        "external_url": row[13],
                        "profile_picture_url": row[14],
                        "category": row[15],
                        "tags_json": row[16],
                        "grid_posts_json": row[17],
                        "vision_analysis_json": row[18],
                        "public_email": row[19],
                        "public_phone_number": row[20],
                        "business_address_json": row[21],
                        "captured_at": row[22],
                        "execution_id": row[23],
                        "trace_id": row[24],
                        "artifact_id": row[25],
                        "schema_version": row[26],
                        "seed_version": row[27],
                        "capture_method": row[28],
                        "run_mode": row[29],
                        "source_context": row[30],
                    },
                )
            if confirmed_target_handles:
                upsert_confirmed_target_handles(
                    conn,
                    workspace_id=workspace_id,
                    handles=confirmed_target_handles,
                )
            conn.commit()
            logger.info(
                f"[IGFollowingAnalyzer] Persisted {len(rows)} accounts to PostgreSQL ig_accounts_flat"
            )
    except Exception as e:
        logger.warning(
            f"[IGFollowingAnalyzer] Failed to persist ig_accounts_flat rows: {e}\n{traceback.format_exc()}"
        )


def persist_follow_edges(
    workspace_id: str,
    seed: str,
    accounts: List[Dict[str, Any]],
    execution_id: Optional[str],
) -> None:
    """
    Persist follow edges to PostgreSQL ig_follow_edges table.

    source_handle = seed (target_username being analyzed)
    target_handle = each account in the following list
    """
    if not workspace_id or not seed or not accounts:
        return

    try:
        engine = _get_db_engine()
    except ImportError as e:
        logger.warning(f"[IGFollowingAnalyzer] Failed to import database module: {e}")
        return

    rows: List[Dict[str, Any]] = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        handle = (account.get("username") or account.get("handle") or "").strip()
        if not handle:
            continue
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "workspace_id": workspace_id,
                "source_handle": seed,  # seed (target_username), NOT login account
                "target_handle": handle,
                "discovered_via_seed": seed,
                "execution_id": execution_id,
            }
        )

    if not rows:
        return

    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            stmt = text(
                """
                INSERT INTO ig_follow_edges (
                    id, workspace_id, source_handle, target_handle,
                    discovered_via_seed, execution_id
                ) VALUES (
                    :id, :workspace_id, :source_handle, :target_handle,
                    :discovered_via_seed, :execution_id
                )
                ON CONFLICT (workspace_id, source_handle, target_handle)
                DO NOTHING
            """
            )
            for row in rows:
                conn.execute(stmt, row)
            conn.commit()
        logger.info(
            f"[IGFollowingAnalyzer] Persisted {len(rows)} follow edges to PostgreSQL"
        )
    except Exception as e:
        logger.warning(
            f"[IGFollowingAnalyzer] Failed to persist ig_follow_edges rows: {e}"
        )


# Legacy aliases for backward compatibility
_persist_accounts_flat = persist_accounts_flat
_persist_follow_edges = persist_follow_edges


def register_seed_immediately(
    workspace_id: str,
    seed: str,
    execution_id: Optional[str] = None,
    source_handle: Optional[str] = None,
    source_profile_ref: Optional[str] = None,
) -> bool:
    """
    Register a seed in ig_accounts_flat immediately when execution starts.

    This ensures the seed appears in the seed list dropdown right away,
    without waiting for accounts to be discovered.

    Writes a placeholder row with the seed as its own handle (self-reference).
    """
    try:
        engine = _get_db_engine()
    except ImportError as e:
        logger.warning(f"[IGFollowingAnalyzer] Failed to import database module: {e}")
        return False

    try:
        from sqlalchemy import text
        from datetime import datetime, timezone

        with engine.connect() as conn:
            # Insert a placeholder row with the seed itself
            # Using UPSERT to avoid duplicates
            stmt = text(
                """
                INSERT INTO ig_accounts_flat (
                    id, workspace_id, seed, source_handle, source_profile_ref,
                    handle, name, captured_at, execution_id, capture_method
                ) VALUES (
                    :id, :workspace_id, :seed, :source_handle, :source_profile_ref,
                    :handle, :name, :captured_at, :execution_id, :capture_method
                )
                ON CONFLICT (workspace_id, seed, handle) DO UPDATE SET
                    source_handle = COALESCE(EXCLUDED.source_handle, ig_accounts_flat.source_handle),
                    source_profile_ref = COALESCE(EXCLUDED.source_profile_ref, ig_accounts_flat.source_profile_ref),
                    execution_id = EXCLUDED.execution_id,
                    capture_method = EXCLUDED.capture_method,
                    captured_at = EXCLUDED.captured_at
            """
            )
            conn.execute(
                stmt,
                {
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "seed": seed,
                    "source_handle": source_handle,
                    "source_profile_ref": source_profile_ref,
                    "handle": f"__seed_placeholder__{seed}",  # Special placeholder handle
                    "name": f"[Seed: {seed}]",
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "execution_id": execution_id,
                    "capture_method": "seed_registration",
                },
            )
            conn.commit()
            logger.info(
                f"[IGFollowingAnalyzer] Registered seed '{seed}' immediately in ig_accounts_flat"
            )
            return True
    except Exception as e:
        logger.warning(
            f"[IGFollowingAnalyzer] Failed to register seed immediately: {e}"
        )
        return False
