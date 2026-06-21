"""Semantic backend sync helpers for intent infrastructure service."""

from __future__ import annotations

import logging
from typing import Any, List

from backend.app.core.domain_context import LocalDomainContext

logger = logging.getLogger(__name__)


class SemanticSyncMixin:
    """Semantic backend sync helper methods for IntentInfraService."""

    async def _sync_to_semantic_hub(
        self,
        ctx: LocalDomainContext,
        intents: List[Any],
        themes: List[Any],
    ):
        """
        Sync intents to semantic-hub Intent Infra.

        Args:
            ctx: Execution context
            intents: List of intents
            themes: List of themes
        """
        if not self.semantic_backend:
            return

        try:
            await self.semantic_backend.push_intents(
                workspace_id=ctx.workspace_id,
                profile_id=ctx.actor_id,
                intents=intents,
                themes=themes,
            )
            logger.info(f"Synced {len(intents)} intents to semantic-hub")
        except Exception as exc:
            logger.warning(f"Failed to sync intents to semantic-hub: {exc}")
