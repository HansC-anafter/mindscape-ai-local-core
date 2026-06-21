import logging
from typing import List, Optional

from backend.app.models.mindscape import MindEvent
from backend.app.services.event_embedding_generator_core.eligibility import (
    map_event_type_to_seed_type,
    should_generate_embedding,
)
from backend.app.services.event_embedding_generator_core.extraction import (
    extract_text_from_event,
)
from backend.app.services.event_embedding_generator_core.providers import (
    generate_embedding,
    generate_embedding_openai,
    generate_embedding_vertex_ai,
)
from backend.app.services.event_embedding_generator_core.storage import (
    check_existing_embedding,
    store_embedding,
)

logger = logging.getLogger("backend.app.services.event_embedding_generator")


class EventEmbeddingGenerator:
    """Generate embeddings for mind events."""

    def __init__(self, store=None):
        """
        Initialize event embedding generator.

        Args:
            store: MindscapeStore instance (optional, will create if not provided)
        """
        if store is None:
            from backend.app.services.mindscape_store import MindscapeStore

            self.store = MindscapeStore()
        else:
            self.store = store

    def should_generate_embedding(self, event: MindEvent) -> bool:
        return should_generate_embedding(event)

    async def generate_embedding_for_event(self, event: MindEvent) -> Optional[str]:
        """
        Generate embedding for an event if it meets criteria.

        Returns seed ID if embedding was created, otherwise None.
        """
        try:
            if not self.should_generate_embedding(event):
                logger.debug(
                    "Skipping embedding for event %s (does not meet criteria)",
                    event.id,
                )
                return None

            text_content = self._extract_text_from_event(event)
            if not text_content:
                logger.debug("No text content in event %s", event.id)
                return None

            existing = self._check_existing_embedding(event)
            if existing:
                logger.debug("Embedding already exists for event %s", event.id)
                return existing

            embedding = await self._generate_embedding(text_content)
            if not embedding:
                logger.warning("Failed to generate embedding for event %s", event.id)
                return None

            seed_id = self._store_embedding(event, text_content, embedding)

            logger.info("Generated embedding for event %s -> seed %s", event.id, seed_id)
            return seed_id

        except Exception as exc:
            logger.error(
                "Failed to generate embedding for event %s: %s",
                event.id,
                exc,
                exc_info=True,
            )
            return None

    def _extract_text_from_event(self, event: MindEvent) -> Optional[str]:
        return extract_text_from_event(event)

    def _check_existing_embedding(self, event: MindEvent) -> Optional[str]:
        return check_existing_embedding(event)

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        return await generate_embedding(text)

    async def _generate_embedding_openai(
        self, model_name: str, text: str
    ) -> Optional[List[float]]:
        return await generate_embedding_openai(model_name, text)

    async def _generate_embedding_vertex_ai(
        self, model_name: str, text: str, settings_store
    ) -> Optional[List[float]]:
        return await generate_embedding_vertex_ai(model_name, text, settings_store)

    def _store_embedding(
        self, event: MindEvent, text: str, embedding: List[float]
    ) -> str:
        return store_embedding(event, text, embedding)

    def _map_event_type_to_seed_type(self, event_type) -> str:
        return map_event_type_to_seed_type(event_type)
