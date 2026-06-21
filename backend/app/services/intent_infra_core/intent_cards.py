"""Intent card helpers for intent infrastructure service."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.mindscape import IntentCard, IntentStatus, PriorityLevel
from backend.app.services.intent_infra_core.time import _utc_now

logger = logging.getLogger(__name__)


class IntentCardsMixin:
    """Intent card helper methods for IntentInfraService."""

    async def _create_intent_cards_from_candidates(
        self,
        ctx: LocalDomainContext,
        intent_candidates: List[Any],
        task_id: str,
        workspace_id: str,
    ) -> int:
        """
        Create IntentCards from intent candidates.

        Args:
            ctx: Execution context
            intent_candidates: List of intent candidates
            task_id: Task ID for metadata
            workspace_id: Workspace ID

        Returns:
            Number of intents added
        """
        intents_added = 0

        for intent_item in intent_candidates[:3]:
            if isinstance(intent_item, dict):
                intent_text = (
                    intent_item.get("title")
                    or intent_item.get("text")
                    or str(intent_item)
                )
            else:
                intent_text = str(intent_item) if intent_item else None

            if (
                not intent_text
                or not isinstance(intent_text, str)
                or len(intent_text.strip()) == 0
            ):
                continue

            try:
                existing_intents = self.store.list_intents(
                    profile_id=ctx.actor_id, status=None, priority=None
                )
                intent_exists = any(
                    intent.title == intent_text.strip()
                    or intent_text.strip() in intent.title
                    for intent in existing_intents
                )

                if not intent_exists:
                    new_intent = IntentCard(
                        id=str(uuid.uuid4()),
                        profile_id=ctx.actor_id,
                        title=intent_text.strip(),
                        description="Added from intent extraction task",
                        status=IntentStatus.PAUSED,
                        priority=PriorityLevel.MEDIUM,
                        tags=[],
                        category="intent_extraction",
                        progress_percentage=0.0,
                        created_at=_utc_now(),
                        updated_at=_utc_now(),
                        started_at=None,
                        completed_at=None,
                        due_date=None,
                        parent_intent_id=None,
                        child_intent_ids=[],
                        metadata={
                            "source": "intent_extraction_task",
                            "workspace_id": workspace_id,
                            "task_id": task_id,
                        },
                    )
                    self.store.create_intent(new_intent)
                    intents_added += 1
                    logger.info(
                        f"Created IntentCard from extraction task: {intent_text[:50]}"
                    )
            except Exception as exc:
                logger.warning(f"Failed to create IntentCard from candidate: {exc}")

        return intents_added

    async def create_intent_card(
        self, ctx: LocalDomainContext, payload: Dict[str, Any]
    ) -> Optional[IntentCard]:
        """
        Create an IntentCard from payload.

        Args:
            ctx: Execution context
            payload: Intent card data

        Returns:
            Created IntentCard or None
        """
        try:
            intent_card = IntentCard(
                id=str(uuid.uuid4()),
                profile_id=ctx.actor_id,
                title=payload.get("title", ""),
                description=payload.get("description", ""),
                status=IntentStatus.ACTIVE,
                priority=PriorityLevel.MEDIUM,
                tags=payload.get("tags", []),
                category=payload.get("category"),
                progress_percentage=0.0,
                created_at=_utc_now(),
                updated_at=_utc_now(),
                started_at=None,
                completed_at=None,
                due_date=None,
                parent_intent_id=None,
                child_intent_ids=[],
                metadata=payload.get("metadata", {}),
            )
            created = self.store.create_intent(intent_card)
            logger.info(f"Created IntentCard via IntentInfraService: {created.id}")
            return created
        except Exception as exc:
            logger.error(f"Failed to create IntentCard: {exc}", exc_info=True)
            return None

    async def list_intents(
        self, ctx: LocalDomainContext, filters: Optional[Dict[str, Any]] = None
    ) -> List[IntentCard]:
        """
        List intents with optional filters.

        Args:
            ctx: Execution context
            filters: Optional filters

        Returns:
            List of IntentCard
        """
        try:
            status = filters.get("status") if filters else None
            priority = filters.get("priority") if filters else None
            category = filters.get("category") if filters else None

            intents = self.store.list_intents(
                profile_id=ctx.actor_id, status=status, priority=priority
            )

            if category:
                intents = [intent for intent in intents if intent.category == category]

            return intents
        except Exception as exc:
            logger.error(f"Failed to list intents: {exc}", exc_info=True)
            return []
