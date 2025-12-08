"""
Intent Embedding Generator Service

Generates embeddings for IntentCards for clustering purposes.
Reuses EventEmbeddingGenerator logic for consistency.
"""

import logging
from typing import List, Optional, Dict
from datetime import datetime

from ...models.mindscape import IntentCard

logger = logging.getLogger(__name__)


class IntentEmbeddingGenerator:
    """Generate embeddings for IntentCards"""

    def __init__(self, store=None):
        """
        Initialize Intent Embedding Generator

        Args:
            store: MindscapeStore instance (optional, will create if not provided)
        """
        if store is None:
            from ...services.mindscape_store import MindscapeStore
            self.store = MindscapeStore()
        else:
            self.store = store

    async def generate_embedding(
        self,
        intent_card: IntentCard
    ) -> Optional[List[float]]:
        """
        Generate embedding for an IntentCard

        Args:
            intent_card: IntentCard to generate embedding for

        Returns:
            Embedding vector (list of floats) or None if generation failed
        """
        try:
            # Extract text content from IntentCard
            text_content = self._extract_text_from_intent(intent_card)
            if not text_content:
                logger.warning(f"No text content in IntentCard {intent_card.id}")
                return None

            # Reuse EventEmbeddingGenerator's embedding generation logic
            from ...services.event_embedding_generator import EventEmbeddingGenerator
            event_generator = EventEmbeddingGenerator(store=self.store)

            embedding = await event_generator._generate_embedding(text_content)

            if embedding:
                logger.info(f"Generated embedding for IntentCard {intent_card.id} (dimension: {len(embedding)})")
            else:
                logger.warning(f"Failed to generate embedding for IntentCard {intent_card.id}")

            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding for IntentCard {intent_card.id}: {e}", exc_info=True)
            return None

    async def generate_embeddings_batch(
        self,
        intent_cards: List[IntentCard]
    ) -> Dict[str, List[float]]:
        """
        Generate embeddings for multiple IntentCards

        Args:
            intent_cards: List of IntentCards

        Returns:
            Dictionary mapping IntentCard ID to embedding vector
        """
        embeddings = {}

        for intent_card in intent_cards:
            embedding = await self.generate_embedding(intent_card)
            if embedding:
                embeddings[intent_card.id] = embedding

        logger.info(f"Generated {len(embeddings)} embeddings from {len(intent_cards)} IntentCards")
        return embeddings

    def _extract_text_from_intent(self, intent_card: IntentCard) -> str:
        """
        Extract text content from IntentCard for embedding

        Args:
            intent_card: IntentCard to extract text from

        Returns:
            Text content string
        """
        text_parts = []

        # Title is most important
        if intent_card.title:
            text_parts.append(f"Title: {intent_card.title}")

        # Description provides context
        if intent_card.description:
            text_parts.append(f"Description: {intent_card.description}")

        # Tags provide categorization
        if intent_card.tags:
            text_parts.append(f"Tags: {', '.join(intent_card.tags)}")

        # Category provides domain context
        if intent_card.category:
            text_parts.append(f"Category: {intent_card.category}")

        # Status and priority provide importance signals
        text_parts.append(f"Status: {intent_card.status.value}, Priority: {intent_card.priority.value}")

        # Metadata may contain additional context
        if intent_card.metadata:
            if intent_card.metadata.get("reasoning"):
                text_parts.append(f"Reasoning: {intent_card.metadata['reasoning']}")
            if intent_card.metadata.get("relation_signals"):
                signals = intent_card.metadata.get("relation_signals", [])
                if signals:
                    text_parts.append(f"Related signals: {len(signals)} signals")

        return "\n".join(text_parts) if text_parts else intent_card.title or ""

