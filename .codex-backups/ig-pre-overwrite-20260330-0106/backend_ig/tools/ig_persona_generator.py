"""
IG Persona Generator Tool

Synthesizes data from ig_account_profiles, ig_posts, and ig_follow_edges
to generate AI-driven user personas using LLM.
"""

import json
import logging
import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _collect_account_data(
    workspace_id: str,
    account_handle: str,
) -> Dict[str, Any]:
    """
    Collect all available data for an account from various tables.
    Returns aggregated data for persona generation.
    """
    data = {
        "handle": account_handle,
        "profile": None,
        "posts": [],
        "network": None,
    }

    try:
        from sqlalchemy import create_engine, text

        try:
            from app.database.config import get_postgres_url_core

            engine = create_engine(get_postgres_url_core())
        except ImportError:
            from backend.app.core.database import get_db_engine

            engine = get_db_engine()
        with engine.connect() as conn:
            # Get profile data
            profile_result = conn.execute(
                text(
                    """
                SELECT account_type, influence_tier, bio_keywords_json,
                       bio, follower_count, following_count, detected_locale
                FROM ig_account_profiles
                WHERE workspace_id = :workspace_id AND account_handle = :handle
                LIMIT 1
            """
                ),
                {"workspace_id": workspace_id, "handle": account_handle},
            )
            row = profile_result.fetchone()
            if row:
                data["profile"] = {
                    "account_type": row[0],
                    "influence_tier": row[1],
                    "bio_keywords": json.loads(row[2]) if row[2] else [],
                    "bio": row[3],
                    "follower_count": row[4],
                    "following_count": row[5],
                    "locale": row[6],
                }

            # Get posts data
            posts_result = conn.execute(
                text(
                    """
                SELECT caption, caption_topic, hashtags_json, like_count
                FROM ig_posts
                WHERE workspace_id = :workspace_id AND account_handle = :handle
                ORDER BY posted_at DESC NULLS LAST
                LIMIT 20
            """
                ),
                {"workspace_id": workspace_id, "handle": account_handle},
            )
            for row in posts_result.fetchall():
                data["posts"].append(
                    {
                        "caption": row[0],
                        "topic": row[1],
                        "hashtags": json.loads(row[2]) if row[2] else [],
                        "likes": row[3],
                    }
                )

            # Get network data (who they follow)
            network_result = conn.execute(
                text(
                    """
                SELECT target_handle FROM ig_follow_edges
                WHERE workspace_id = :workspace_id AND source_handle = :handle
                LIMIT 50
            """
                ),
                {"workspace_id": workspace_id, "handle": account_handle},
            )
            follows = [row[0] for row in network_result.fetchall()]
            if follows:
                data["network"] = {"follows": follows}

    except Exception as e:
        logger.warning(
            f"[IGPersonaGenerator] Failed to collect data for {account_handle}: {e}"
        )

    return data


def _build_llm_prompt(account_data: Dict[str, Any]) -> str:
    """Build the prompt for LLM persona generation."""
    profile = account_data.get("profile") or {}
    posts = account_data.get("posts") or []

    # Summarize post content
    topics = [p.get("topic") for p in posts if p.get("topic")]
    topic_summary = ", ".join(set(topics)) if topics else "unknown"

    # Sample hashtags
    all_hashtags = []
    for p in posts:
        all_hashtags.extend(p.get("hashtags", [])[:5])
    hashtag_sample = ", ".join(set(all_hashtags)[:15])

    # Sample captions (first sentences)
    caption_samples = []
    for p in posts[:5]:
        caption = p.get("caption") or ""
        if caption:
            first_sentence = caption.split(".")[0][:100]
            caption_samples.append(first_sentence)

    prompt = f"""Analyze this Instagram account and generate a user persona:

## Account Profile
- Handle: @{account_data.get('handle')}
- Account Type: {profile.get('account_type', 'unknown')}
- Influence Tier: {profile.get('influence_tier', 'unknown')}
- Bio: {profile.get('bio', 'N/A')[:200]}
- Bio Keywords: {', '.join(profile.get('bio_keywords', [])[:10])}
- Followers: {profile.get('follower_count', 'N/A')}
- Following: {profile.get('following_count', 'N/A')}
- Detected Locale: {profile.get('locale', 'unknown')}

## Content Analysis
- Post Topics: {topic_summary}
- Common Hashtags: {hashtag_sample}
- Sample Captions: {' | '.join(caption_samples)}

## Output Requirements
Generate a structured JSON with:
1. persona_summary: 2-3 sentence summary of this user's persona
2. key_traits: Array of 3-5 key personality/content traits
3. content_themes: Array of primary content themes
4. demographics: Object with estimated age_range, gender, location_type
5. collaboration_potential: Score 0-1 for brand collaboration fit
6. recommended_approach: How should a brand approach this user"""

    return prompt


async def ig_persona_generator(
    workspace_id: str,
    target_handles: List[str],
    mode: str = "collect",  # "collect" | "generate" | "persist"
    account_data_from_collect: Optional[List[Dict[str, Any]]] = None,
    personas_from_llm: Optional[List[Dict[str, Any]]] = None,
    model: str = "gpt-4o-mini",
    batch_size: int = 10,
) -> Dict[str, Any]:
    """
    Generate AI-driven personas from collected IG data.

    Modes (3-step Playbook pattern):
    - collect: Gather data from tables, return for LLM input
    - generate: (Called by Playbook) Return prompts for LLM
    - persist: Write LLM results to ig_generated_personas

    Args:
        workspace_id: Workspace ID
        target_handles: Accounts to generate personas for
        mode: Operation mode
        account_data_from_collect: Data from collect step
        personas_from_llm: Persona results from LLM step
        model: LLM model used (for metadata)
        batch_size: Max accounts per batch
    """
    logger.info(f"[IGPersonaGenerator] Starting persona generation")
    logger.info(f"  workspace_id: {workspace_id}")
    logger.info(f"  target_handles: {len(target_handles)} accounts")
    logger.info(f"  mode: {mode}")

    # Mode: collect - gather data from tables
    if mode == "collect":
        collected = []
        for handle in target_handles[:batch_size]:
            data = _collect_account_data(workspace_id, handle)
            if data.get("profile"):  # Only include accounts with profile data
                data["prompt"] = _build_llm_prompt(data)
                collected.append(data)

        return {
            "status": "success",
            "mode": "collect",
            "account_data": collected,
            "prompts": [d["prompt"] for d in collected],
            "collected_count": len(collected),
        }

    # Mode: persist - write LLM results to database
    elif mode == "persist":
        if not personas_from_llm:
            return {
                "status": "error",
                "error": "persist mode requires personas_from_llm",
            }

        persisted_count = 0
        try:
            from sqlalchemy import create_engine, text

            try:
                from app.database.config import get_postgres_url_core

                engine = create_engine(get_postgres_url_core())
            except ImportError:
                from backend.app.core.database import get_db_engine

                engine = get_db_engine()
            with engine.connect() as conn:
                for persona in personas_from_llm:
                    handle = persona.get("handle")
                    if not handle:
                        continue

                    stmt = text(
                        """
                        INSERT INTO ig_generated_personas (
                            id, workspace_id, account_handle,
                            persona_summary, persona_locale,
                            key_traits_json, content_themes_json, demographics_json,
                            brand_affinity_scores_json, collaboration_potential,
                            recommended_approach, model_used, input_data_version
                        ) VALUES (
                            :id, :workspace_id, :account_handle,
                            :persona_summary, :persona_locale,
                            :key_traits_json, :content_themes_json, :demographics_json,
                            :brand_affinity_scores_json, :collaboration_potential,
                            :recommended_approach, :model_used, :input_data_version
                        )
                        ON CONFLICT (workspace_id, account_handle)
                        DO UPDATE SET
                            persona_summary = EXCLUDED.persona_summary,
                            key_traits_json = EXCLUDED.key_traits_json,
                            content_themes_json = EXCLUDED.content_themes_json,
                            demographics_json = EXCLUDED.demographics_json,
                            collaboration_potential = EXCLUDED.collaboration_potential,
                            recommended_approach = EXCLUDED.recommended_approach,
                            model_used = EXCLUDED.model_used,
                            generated_at = CURRENT_TIMESTAMP
                    """
                    )

                    conn.execute(
                        stmt,
                        {
                            "id": str(uuid.uuid4()),
                            "workspace_id": workspace_id,
                            "account_handle": handle,
                            "persona_summary": persona.get("persona_summary"),
                            "persona_locale": persona.get("persona_locale"),
                            "key_traits_json": json.dumps(
                                persona.get("key_traits", []), ensure_ascii=False
                            ),
                            "content_themes_json": json.dumps(
                                persona.get("content_themes", []), ensure_ascii=False
                            ),
                            "demographics_json": json.dumps(
                                persona.get("demographics", {}), ensure_ascii=False
                            ),
                            "brand_affinity_scores_json": json.dumps(
                                persona.get("brand_affinity_scores", {}),
                                ensure_ascii=False,
                            ),
                            "collaboration_potential": persona.get(
                                "collaboration_potential"
                            ),
                            "recommended_approach": persona.get("recommended_approach"),
                            "model_used": model,
                            "input_data_version": _utc_now().strftime("%Y%m%d"),
                        },
                    )
                    persisted_count += 1

                conn.commit()

        except Exception as e:
            logger.error(f"[IGPersonaGenerator] Database error: {e}")
            return {"status": "error", "error": str(e)}

        return {
            "status": "success",
            "mode": "persist",
            "persisted_count": persisted_count,
        }

    else:
        return {
            "status": "error",
            "error": f"Unknown mode: {mode}",
        }
