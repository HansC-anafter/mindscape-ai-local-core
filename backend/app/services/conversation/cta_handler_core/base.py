"""Shared dependencies for CTA handler composition."""

from datetime import datetime, timezone

from ...i18n_service import get_i18n_service
from ...mindscape_store import MindscapeStore
from ...stores.tasks_store import TasksStore
from ...stores.timeline_items_store import TimelineItemsStore


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class CTAHandlerBase:
    """Initialize shared CTA handler dependencies."""

    def __init__(
        self,
        store: MindscapeStore,
        tasks_store: TasksStore,
        timeline_items_store: TimelineItemsStore,
        plan_builder,
        default_locale: str = "en",
    ):
        """
        Initialize CTAHandler.

        Args:
            store: MindscapeStore instance.
            tasks_store: TasksStore instance.
            timeline_items_store: TimelineItemsStore instance.
            plan_builder: PlanBuilder instance.
            default_locale: Default locale for i18n.
        """
        self.store = store
        self.tasks_store = tasks_store
        self.timeline_items_store = timeline_items_store
        self.plan_builder = plan_builder
        self.i18n = get_i18n_service(default_locale=default_locale)
