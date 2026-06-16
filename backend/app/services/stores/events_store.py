"""
Events store for Mindscape data persistence
Handles mind events (timeline) CRUD operations
"""

from typing import List
import logging

from backend.app.services.stores.base import StoreBase
from backend.app.services.stores.events_projection import (
    row_to_event,
    rows_to_events,
)
from backend.app.services.stores.events_store_queries import EventsStoreQueryMixin
from backend.app.services.stores.events_store_writes import EventsStoreWriteMixin
from ...models.mindscape import MindEvent

logger = logging.getLogger(__name__)


class EventsStore(EventsStoreWriteMixin, EventsStoreQueryMixin, StoreBase):
    """Store for managing mind events"""

    def _row_to_event(self, row) -> MindEvent:
        return row_to_event(
            row,
            deserialize_json=self.deserialize_json,
            from_isoformat=self.from_isoformat,
            logger=logger,
        )

    def _rows_to_events(self, rows, context: str) -> List[MindEvent]:
        return rows_to_events(
            rows,
            row_to_event=self._row_to_event,
            context=context,
            logger=logger,
        )
