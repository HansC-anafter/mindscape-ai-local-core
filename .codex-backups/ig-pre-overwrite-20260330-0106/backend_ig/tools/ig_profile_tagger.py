"""
IG Profile Tagger Tool

Computes profile tags (account type, influence tier, bio keywords) from ig_accounts_flat
and persists to ig_account_profiles table.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from capabilities.ig.source_filters import confirmed_target_condition_sql


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Influence tier thresholds based on follower count
INFLUENCE_TIERS = [
    (1_000_000, "mega"),
    (100_000, "macro"),
    (10_000, "mid"),
    (1_000, "micro"),
    (0, "nano"),
]

# Brand indicators in bio
BRAND_INDICATORS = [
    "official",
    "®",
    "™",
    "brand",
    "company",
    "inc.",
    "ltd",
    "llc",
    "shop",
    "store",
    "boutique",
    "官方",
    "品牌",
    "授權",
    "代理",
]

# KOL indicators in bio
KOL_INDICATORS = [
    "creator",
    "influencer",
    "blogger",
    "vlogger",
    "content",
    "collab",
    "dm for",
    "business",
    "inquiries",
    "合作",
    "開箱",
    "業配",
    "邀約",
    "kol",
    "youtuber",
    "網紅",
    "部落客",
]

# Media indicators in bio
MEDIA_INDICATORS = [
    "news",
    "media",
    "magazine",
    "tv",
    "radio",
    "podcast",
    "journalist",
    "editor",
    "新聞",
    "媒體",
    "頻道",
    "電台",
]

# Contact indicators
CONTACT_INDICATORS = [
    "email",
    "dm",
    "line",
    "@",
    "wechat",
    "whatsapp",
    "telegram",
    "聯繫",
    "洽詢",
    "私訊",
]


def _classify_influence_tier(follower_count: Optional[int]) -> str:
    """Classify influence tier based on follower count."""
    if follower_count is None or follower_count < 0:
        return "unknown"
    for threshold, tier in INFLUENCE_TIERS:
        if follower_count >= threshold:
            return tier
    return "nano"


def _classify_account_type(
    bio: Optional[str],
    is_verified: Optional[bool],
    follower_count: Optional[int],
    following_count: Optional[int],
    category: Optional[str],
) -> str:
    """
    Classify account type based on bio content and account metrics.

    Types: kol, brand, personal, media, unknown
    """
    bio_lower = (bio or "").lower()

    # Check for media first
    if any(indicator in bio_lower for indicator in MEDIA_INDICATORS):
        return "media"

    # Check for brand
    if any(indicator in bio_lower for indicator in BRAND_INDICATORS):
        return "brand"

    # Verified accounts with high followers are likely KOL/brand
    if is_verified:
        if follower_count and follower_count > 50_000:
            # Check if KOL indicators present
            if any(indicator in bio_lower for indicator in KOL_INDICATORS):
                return "kol"
            return "brand"  # Default verified high-follower to brand

    # Check for KOL
    if any(indicator in bio_lower for indicator in KOL_INDICATORS):
        return "kol"

    # Follower/following ratio analysis
    if follower_count and following_count and following_count > 0:
        ratio = follower_count / following_count
        if ratio > 10 and follower_count > 5_000:
            return "kol"  # High ratio suggests influencer

    # Category from IG can help
    if category:
        cat_lower = category.lower()
        if any(x in cat_lower for x in ["creator", "blogger", "influencer", "artist"]):
            return "kol"
        if any(x in cat_lower for x in ["brand", "product", "clothing", "business"]):
            return "brand"
        if any(x in cat_lower for x in ["media", "news", "magazine"]):
            return "media"

    # Default to personal if has normal engagement
    if follower_count and follower_count > 100:
        return "personal"

    return "unknown"


def _extract_bio_keywords(bio: Optional[str]) -> List[str]:
    """
    Extract keywords from bio using simple tokenization.
    For Chinese text, uses jieba if available.
    """
    if not bio:
        return []

    keywords = []

    # Try jieba for Chinese text
    try:
        import jieba

        # Check if bio contains Chinese characters
        if re.search(r"[\u4e00-\u9fff]", bio):
            words = list(jieba.cut(bio))
            keywords.extend([w.strip() for w in words if len(w.strip()) > 1])
    except ImportError:
        pass

    # Simple extraction for non-Chinese
    # Extract hashtags
    hashtags = re.findall(r"#(\w+)", bio)
    keywords.extend(hashtags)

    # Extract @mentions
    mentions = re.findall(r"@(\w+)", bio)
    keywords.extend(mentions)

    # Extract words (basic tokenization)
    words = re.findall(r"\b[a-zA-Z]{3,}\b", bio.lower())
    # Filter common stopwords
    stopwords = {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "her",
        "was",
    }
    keywords.extend([w for w in words if w not in stopwords])

    # Deduplicate while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            unique_keywords.append(kw)

    return unique_keywords[:20]  # Limit to 20 keywords


def _detect_bio_locale(bio: Optional[str]) -> str:
    """Detect primary language of bio."""
    if not bio:
        return "unknown"

    try:
        from langdetect import detect

        return detect(bio)
    except Exception:
        # Fallback: check for CJK characters
        if re.search(r"[\u4e00-\u9fff]", bio):
            return "zh"
        if re.search(r"[\u3040-\u309f\u30a0-\u30ff]", bio):
            return "ja"
        if re.search(r"[\uac00-\ud7af]", bio):
            return "ko"
        return "en"


def _has_contact_info(bio: Optional[str]) -> bool:
    """Check if bio contains contact information."""
    if not bio:
        return False
    bio_lower = bio.lower()
    return any(indicator in bio_lower for indicator in CONTACT_INDICATORS)


def _has_external_link(external_url: Optional[str], bio: Optional[str]) -> bool:
    """Check if account has external link."""
    if external_url:
        return True
    if bio and re.search(r"https?://", bio):
        return True
    return False


def _compute_activity_score(
    post_count: Optional[int],
    follower_count: Optional[int],
    following_count: Optional[int],
) -> Optional[float]:
    """
    Compute a simple activity score (0-1).
    Based on post frequency relative to account age approximation.
    """
    if not post_count or post_count <= 0:
        return None
    if not follower_count:
        return None

    # Simple heuristic: posts per 1000 followers, normalized
    posts_per_k = post_count / max(follower_count / 1000, 1)
    # Clamp between 0 and 1
    return min(1.0, max(0.0, posts_per_k / 100))


async def ig_profile_tagger(
    workspace_id: str,
    seed: str,
    force_recompute: bool = False,
    batch_size: int = 100,
) -> Dict[str, Any]:
    """
    Compute profile tags from ig_accounts_flat and persist to ig_account_profiles.

    Args:
        workspace_id: Workspace ID for data partitioning
        seed: Target seed account (the account whose following list was analyzed)
        force_recompute: If True, recompute even if profile already exists
        batch_size: Number of records to process per batch

    Returns:
        Summary of processing results
    """
    logger.info(f"[IGProfileTagger] Starting profile tagging")
    logger.info(f"  workspace_id: {workspace_id}")
    logger.info(f"  seed: {seed}")
    logger.info(f"  force_recompute: {force_recompute}")

    # Import database session
    try:
        from sqlalchemy import create_engine, text

        # Try local-core database config first
        try:
            from app.database.config import get_postgres_url_core

            engine = create_engine(get_postgres_url_core())
        except ImportError:
            # Fallback for cloud environment
            from backend.app.core.database import get_db_engine

            engine = get_db_engine()
    except ImportError as e:
        logger.error(f"[IGProfileTagger] Failed to import database module: {e}")
        return {
            "status": "error",
            "error": f"Database module import failed: {e}",
        }

    processed_count = 0
    created_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0

    try:
        with engine.connect() as conn:
            # Query latest snapshots from ig_accounts_flat
            # Group by handle, get the one with max captured_at
            query = text(
                """
                SELECT DISTINCT ON (handle)
                    id, handle, name, is_verified, follower_count, following_count,
                    post_count, bio, external_url, category, captured_at
                FROM ig_accounts_flat
                WHERE workspace_id = :workspace_id
                  AND seed = :seed
                  AND """
                + confirmed_target_condition_sql()
                + """
                ORDER BY handle, captured_at DESC
            """
            )

            result = conn.execute(query, {"workspace_id": workspace_id, "seed": seed})
            rows = result.fetchall()

            logger.info(f"[IGProfileTagger] Found {len(rows)} accounts to process")

            for row in rows:
                try:
                    snapshot_id = row[0]
                    handle = row[1]
                    name = row[2]
                    is_verified = row[3]
                    follower_count = row[4]
                    following_count = row[5]
                    post_count = row[6]
                    bio = row[7]
                    external_url = row[8]
                    category = row[9]

                    # Check if already exists (skip if not force_recompute)
                    if not force_recompute:
                        check_query = text(
                            """
                            SELECT id FROM ig_account_profiles
                            WHERE workspace_id = :workspace_id
                              AND seed = :seed
                              AND account_handle = :handle
                        """
                        )
                        existing = conn.execute(
                            check_query,
                            {
                                "workspace_id": workspace_id,
                                "seed": seed,
                                "handle": handle,
                            },
                        ).fetchone()

                        if existing:
                            skipped_count += 1
                            continue

                    # Compute profile tags
                    account_type = _classify_account_type(
                        bio, is_verified, follower_count, following_count, category
                    )
                    influence_tier = _classify_influence_tier(follower_count)

                    # Compute ratios
                    ff_ratio = None
                    if follower_count and following_count and following_count > 0:
                        ff_ratio = follower_count / following_count

                    # Extract bio info
                    bio_keywords = _extract_bio_keywords(bio)
                    bio_locale = _detect_bio_locale(bio)
                    bio_has_contact = _has_contact_info(bio)
                    bio_has_link = _has_external_link(external_url, bio)

                    # Compute scores
                    activity_score = _compute_activity_score(
                        post_count, follower_count, following_count
                    )

                    # Simple engagement potential (placeholder - would need historical data)
                    engagement_potential = None
                    if follower_count and follower_count > 0:
                        # Rough estimate based on tier
                        tier_multipliers = {
                            "nano": 0.08,
                            "micro": 0.05,
                            "mid": 0.03,
                            "macro": 0.02,
                            "mega": 0.01,
                        }
                        engagement_potential = tier_multipliers.get(
                            influence_tier, 0.02
                        )

                    # Upsert to ig_account_profiles
                    profile_id = str(uuid.uuid4())

                    upsert_stmt = text(
                        """
                        INSERT INTO ig_account_profiles (
                            id, workspace_id, seed, account_handle,
                            account_type, influence_tier,
                            engagement_potential, follower_following_ratio, activity_score,
                            bio_keywords_json, bio_detected_locale, bio_has_contact, bio_has_link,
                            source_snapshot_id, computed_at, schema_version
                        ) VALUES (
                            :id, :workspace_id, :seed, :handle,
                            :account_type, :influence_tier,
                            :engagement_potential, :ff_ratio, :activity_score,
                            :bio_keywords_json, :bio_locale, :bio_has_contact, :bio_has_link,
                            :snapshot_id, :computed_at, :schema_version
                        )
                        ON CONFLICT (workspace_id, seed, account_handle)
                        DO UPDATE SET
                            account_type = EXCLUDED.account_type,
                            influence_tier = EXCLUDED.influence_tier,
                            engagement_potential = EXCLUDED.engagement_potential,
                            follower_following_ratio = EXCLUDED.follower_following_ratio,
                            activity_score = EXCLUDED.activity_score,
                            bio_keywords_json = EXCLUDED.bio_keywords_json,
                            bio_detected_locale = EXCLUDED.bio_detected_locale,
                            bio_has_contact = EXCLUDED.bio_has_contact,
                            bio_has_link = EXCLUDED.bio_has_link,
                            source_snapshot_id = EXCLUDED.source_snapshot_id,
                            computed_at = EXCLUDED.computed_at
                    """
                    )

                    conn.execute(
                        upsert_stmt,
                        {
                            "id": profile_id,
                            "workspace_id": workspace_id,
                            "seed": seed,
                            "handle": handle,
                            "account_type": account_type,
                            "influence_tier": influence_tier,
                            "engagement_potential": engagement_potential,
                            "ff_ratio": ff_ratio,
                            "activity_score": activity_score,
                            "bio_keywords_json": (
                                json.dumps(bio_keywords, ensure_ascii=False)
                                if bio_keywords
                                else None
                            ),
                            "bio_locale": bio_locale,
                            "bio_has_contact": bio_has_contact,
                            "bio_has_link": bio_has_link,
                            "snapshot_id": snapshot_id,
                            "computed_at": _utc_now(),
                            "schema_version": "ig.profile.v1",
                        },
                    )

                    processed_count += 1
                    if force_recompute:
                        updated_count += 1
                    else:
                        created_count += 1

                except Exception as e:
                    logger.warning(f"[IGProfileTagger] Error processing {handle}: {e}")
                    error_count += 1
                    continue

            conn.commit()

    except Exception as e:
        logger.error(f"[IGProfileTagger] Database error: {e}")
        return {
            "status": "error",
            "error": str(e),
        }

    result = {
        "status": "success",
        "workspace_id": workspace_id,
        "seed": seed,
        "processed": processed_count,
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "errors": error_count,
        "computed_at": _utc_now().isoformat(),
    }

    logger.info(f"[IGProfileTagger] Completed: {result}")
    return result
