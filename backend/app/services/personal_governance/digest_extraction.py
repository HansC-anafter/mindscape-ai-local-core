"""
DigestExtractionService — Extract PersonalKnowledge + GoalLedger entries from SessionDigest.

ADR-001 v2 Phase 2: Goal Extraction Pipeline.

This service processes a SessionDigest and extracts:
  - PersonalKnowledge candidates (preferences, principles, goals)
  - GoalLedgerEntry candidates (new goals, goal updates)

All writes follow the Writeback Policy Spec:
  - Goals: max 3 per session, enter as pending_confirmation, 7-day cooldown
  - Knowledge: max 5/week per workspace, enter as candidate, dedup > 0.85
  - Every write produces a WritebackReceipt
"""

import json
import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.models.personal_governance.goal_ledger import GoalLedgerEntry
from backend.app.models.personal_governance.personal_knowledge import (
    PersonalKnowledge,
)
from backend.app.models.personal_governance.session_digest import SessionDigest
from backend.app.models.personal_governance.writeback_receipt import WritebackReceipt
from backend.app.services.stores.postgres.goal_ledger_store import GoalLedgerStore
from backend.app.services.stores.postgres.personal_knowledge_store import (
    PersonalKnowledgeStore,
)
from backend.app.services.stores.postgres.session_digest_store import (
    SessionDigestStore,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Extraction prompt (structured JSON output)
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """\
You are a personal knowledge extraction agent. Given a session digest (summary of a meeting or chat session), extract:

1. **personal_knowledge**: Lasting insights about the user — preferences, principles, values, recurring patterns, or self-knowledge. Only extract items that are likely to remain true beyond this session.
2. **goals**: Goals or objectives the user mentioned or implied. These can be new goals or updates to existing ones.

Rules:
- Only extract genuinely personal, lasting knowledge — NOT tactical decisions or one-time actions.
- Goals must be concrete enough to track progress on.
- Confidence: 0.0–1.0, where 1.0 = explicitly stated by user, 0.5 = inferred.
- For knowledge_type, use one of: goal, preference, principle, value, pattern, skill, context.
- For goal horizon, use one of: weekly, monthly, quarterly, yearly, open-ended.

Respond ONLY with valid JSON:
{
  "personal_knowledge": [
    {"content": "...", "knowledge_type": "preference|principle|value|pattern|skill|context", "confidence": 0.8}
  ],
  "goals": [
    {"title": "...", "description": "...", "horizon": "monthly|quarterly|yearly|open-ended", "confidence": 0.7}
  ]
}

If nothing extractable, return: {"personal_knowledge": [], "goals": []}
"""


def _build_extraction_user_prompt(digest: SessionDigest) -> str:
    """Build user prompt from digest content."""
    parts = [f"## Session Summary\n{digest.summary_md}"]

    if digest.claims:
        claim_lines = [f"- {c.get('content', '')}" for c in digest.claims[:10]]
        parts.append(f"## User Claims\n" + "\n".join(claim_lines))

    if digest.actions:
        action_lines = [
            f"- {a.get('title', '')}: {a.get('description', '')}"
            for a in digest.actions[:10]
        ]
        parts.append(f"## Action Items\n" + "\n".join(action_lines))

    if digest.decisions:
        dec_lines = [
            f"- {d.get('event_id', d.get('content', str(d)))}"
            for d in digest.decisions[:10]
        ]
        parts.append(f"## Decisions\n" + "\n".join(dec_lines))

    parts.append(
        f"\nSource: {digest.source_type} | Workspaces: {digest.workspace_refs}"
    )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# LLM call (pluggable — uses Ollama or OpenAI via existing config)
# ---------------------------------------------------------------------------


async def _call_extraction_llm(
    system_prompt: str, user_prompt: str
) -> Optional[Dict[str, Any]]:
    """Call LLM for structured extraction. Returns parsed JSON or None."""
    try:
        import httpx
        import os

        # Try Ollama first (local, fast)
        ollama_host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
        model = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{ollama_host}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
            )
            if resp.status_code == 200:
                content = resp.json().get("message", {}).get("content", "")
                return json.loads(content)
    except Exception as e:
        logger.debug("Ollama extraction failed, trying OpenAI: %s", e)

    # Fallback: OpenAI
    try:
        from backend.app.services.config_store import ConfigStore
        import openai
        import os

        config_store = ConfigStore()
        config = config_store.get_or_create_config("default-user")
        api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("No LLM available for extraction")
            return None

        client = openai.AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1000,
        )
        content = resp.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        logger.error("OpenAI extraction failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Main extraction service
# ---------------------------------------------------------------------------


class DigestExtractionService:
    """Process SessionDigest → PersonalKnowledge + GoalLedger entries.

    Enforces writeback policy cooldowns and dedup rules.
    """

    def __init__(self):
        self.pk_store = PersonalKnowledgeStore()
        self.gl_store = GoalLedgerStore()
        self.digest_store = SessionDigestStore()

    async def extract_from_digest(
        self, digest: SessionDigest, meta_session_id: str = ""
    ) -> Dict[str, Any]:
        """Run extraction pipeline on a single digest.

        Returns summary of what was extracted and persisted.
        """
        result = {
            "digest_id": digest.id,
            "knowledge_created": 0,
            "goals_created": 0,
            "skipped_cooldown": 0,
            "skipped_dedup": 0,
            "receipts": [],
        }

        # Skip if digest is too thin
        if len(digest.summary_md) < 50:
            logger.info(
                "Digest %s too thin for extraction (%d chars)",
                digest.id,
                len(digest.summary_md),
            )
            return result

        # Call LLM
        user_prompt = _build_extraction_user_prompt(digest)
        extraction = await _call_extraction_llm(EXTRACTION_SYSTEM_PROMPT, user_prompt)

        if not extraction:
            logger.warning("LLM extraction returned nothing for digest %s", digest.id)
            return result

        # Process knowledge candidates
        knowledge_items = extraction.get("personal_knowledge", [])
        for item in knowledge_items[:5]:  # hard cap
            receipt = self._process_knowledge_item(item, digest, meta_session_id)
            if receipt:
                result["receipts"].append(receipt)
                if receipt.status == "completed":
                    result["knowledge_created"] += 1
                elif receipt.status == "skipped_dedup":
                    result["skipped_dedup"] += 1
                elif receipt.status == "skipped_cooldown":
                    result["skipped_cooldown"] += 1

        # Process goal candidates
        goal_items = extraction.get("goals", [])
        goals_written = 0
        for item in goal_items[:5]:  # hard cap
            if goals_written >= 3:  # writeback policy: max 3 goals per session
                break
            receipt = self._process_goal_item(item, digest, meta_session_id)
            if receipt:
                result["receipts"].append(receipt)
                if receipt.status == "completed":
                    result["goals_created"] += 1
                    goals_written += 1
                elif receipt.status == "skipped_cooldown":
                    result["skipped_cooldown"] += 1

        logger.info(
            "Extraction for digest %s: %d knowledge, %d goals, %d skipped",
            digest.id,
            result["knowledge_created"],
            result["goals_created"],
            result["skipped_cooldown"] + result["skipped_dedup"],
        )
        return result

    def _process_knowledge_item(
        self,
        item: Dict[str, Any],
        digest: SessionDigest,
        meta_session_id: str,
    ) -> Optional[WritebackReceipt]:
        """Process a single knowledge extraction result."""
        content = item.get("content", "").strip()
        if not content or len(content) < 10:
            return None

        confidence = min(1.0, max(0.0, item.get("confidence", 0.5)))
        if confidence < 0.5:
            return None  # below threshold

        knowledge_type = item.get("knowledge_type", "preference")

        # Dedup check
        existing = self.pk_store.find_similar_content(digest.owner_profile_id, content)
        if existing:
            return WritebackReceipt(
                meta_session_id=meta_session_id,
                source_decision_id=digest.id,
                target_table="personal_knowledge",
                target_id=existing.id,
                writeback_type="dedup_skip",
                status="skipped_dedup",
            )

        # Per-workspace throttle: max 5 candidates/week
        for ws_id in digest.workspace_refs[:1]:
            since = _utc_now() - timedelta(days=7)
            count = self.pk_store.count_candidates_since(
                digest.owner_profile_id, ws_id, since
            )
            if count >= 5:
                return WritebackReceipt(
                    meta_session_id=meta_session_id,
                    source_decision_id=digest.id,
                    target_table="personal_knowledge",
                    target_id="",
                    writeback_type="throttle_skip",
                    status="skipped_cooldown",
                )

        # Create candidate
        entry = PersonalKnowledge(
            owner_profile_id=digest.owner_profile_id,
            knowledge_type=knowledge_type,
            content=content,
            status="candidate",
            confidence=confidence,
            source_evidence=[
                {"digest_id": digest.id, "source_type": digest.source_type}
            ],
            source_workspace_ids=digest.workspace_refs,
            valid_scope="global",
            metadata={"extraction_source": "digest_extraction_v1"},
        )
        self.pk_store.create(entry)

        return WritebackReceipt(
            meta_session_id=meta_session_id,
            source_decision_id=digest.id,
            target_table="personal_knowledge",
            target_id=entry.id,
            writeback_type="candidate",
            status="completed",
        )

    def _process_goal_item(
        self,
        item: Dict[str, Any],
        digest: SessionDigest,
        meta_session_id: str,
    ) -> Optional[WritebackReceipt]:
        """Process a single goal extraction result."""
        title = item.get("title", "").strip()
        if not title or len(title) < 5:
            return None

        confidence = min(1.0, max(0.0, item.get("confidence", 0.5)))
        if confidence < 0.6:
            return None  # goals need higher confidence

        # Check if similar goal already exists (by title substring match)
        existing_goals = self.gl_store.list_by_owner(digest.owner_profile_id, limit=50)
        for g in existing_goals:
            if title.lower() in g.title.lower() or g.title.lower() in title.lower():
                # Check 7-day cooldown
                if g.last_updated_at and (_utc_now() - g.last_updated_at) < timedelta(
                    days=7
                ):
                    return WritebackReceipt(
                        meta_session_id=meta_session_id,
                        source_decision_id=digest.id,
                        target_table="goal_ledger",
                        target_id=g.id,
                        writeback_type="cooldown_skip",
                        status="skipped_cooldown",
                    )

        # Create new goal as pending_confirmation
        entry = GoalLedgerEntry(
            owner_profile_id=digest.owner_profile_id,
            title=title,
            description=item.get("description", ""),
            status="pending_confirmation",
            horizon=item.get("horizon", "open-ended"),
            source_digest_ids=[digest.id],
            related_knowledge_ids=[],
            metadata={
                "extraction_source": "digest_extraction_v1",
                "confidence": confidence,
            },
        )
        self.gl_store.create(entry)

        return WritebackReceipt(
            meta_session_id=meta_session_id,
            source_decision_id=digest.id,
            target_table="goal_ledger",
            target_id=entry.id,
            writeback_type="pending_confirmation",
            status="completed",
        )


# ---------------------------------------------------------------------------
# Convenience: fire-and-forget trigger after digest creation
# ---------------------------------------------------------------------------


async def trigger_extraction(digest: SessionDigest, meta_session_id: str = "") -> None:
    """Fire-and-forget extraction trigger. Safe to call from close hooks."""
    try:
        svc = DigestExtractionService()
        result = await svc.extract_from_digest(digest, meta_session_id)

        # Persist receipts
        if result["receipts"]:
            try:
                from backend.app.services.stores.postgres_base import PostgresStoreBase
                from sqlalchemy import text

                base = PostgresStoreBase()
                for r in result["receipts"]:
                    with base.transaction() as conn:
                        conn.execute(
                            text(
                                """
                                INSERT INTO writeback_receipts
                                (id, meta_session_id, source_decision_id, target_table,
                                 target_id, writeback_type, status, created_at)
                                VALUES (:id, :msid, :sdid, :tt, :tid, :wt, :st, now())
                            """
                            ),
                            {
                                "id": r.id,
                                "msid": r.meta_session_id,
                                "sdid": r.source_decision_id,
                                "tt": r.target_table,
                                "tid": r.target_id,
                                "wt": r.writeback_type,
                                "st": r.status,
                            },
                        )
            except Exception as exc:
                logger.warning("Failed to persist writeback receipts: %s", exc)

        logger.info(
            "Extraction complete for digest %s: +%d knowledge, +%d goals",
            digest.id,
            result["knowledge_created"],
            result["goals_created"],
        )
    except Exception as exc:
        logger.warning("Extraction trigger failed for digest %s: %s", digest.id, exc)
