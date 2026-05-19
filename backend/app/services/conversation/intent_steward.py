"""Intent steward facade."""

from typing import Any, List, Optional

from backend.app.models.mindscape import (
    IntentCard,
    IntentLayoutPlan,
    IntentSignal,
    IntentStewardInput,
)
from backend.app.services.conversation.intent_steward_core.analysis import (
    steward_analyze as steward_analyze_helper,
)
from backend.app.services.conversation.intent_steward_core.analysis_log import (
    write_analysis_log,
)
from backend.app.services.conversation.intent_steward_core.execution import (
    check_auto_layout_flag,
    execute_layout_plan,
)
from backend.app.services.conversation.intent_steward_core.filtering import (
    find_similar_intent,
    prefilter_signals,
)
from backend.app.services.conversation.intent_steward_core.input_collection import (
    collect_input_data,
)
from backend.app.services.conversation.intent_steward_core.llm_analysis import (
    llm_analyze_signals,
)
from backend.app.services.conversation.intent_steward_core.runtime import (
    analyze_turn,
    utc_now,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.intent_tags_store import IntentTagsStore
from backend.app.services.stores.postgres.events_store import PostgresEventsStore
from backend.app.services.stores.postgres.timeline_items_store import (
    PostgresTimelineItemsStore,
)


def _utc_now():
    """Return timezone-aware UTC now."""
    return utc_now()


class IntentStewardService:
    """Analyze conversation turns and generate IntentLayoutPlan."""

    MAX_CREATE_INTENT_CARDS = 3
    MAX_UPDATE_INTENT_CARDS = 5
    MIN_CONFIDENCE_THRESHOLD = 0.7
    MAX_PREFILTERED_SIGNALS = 20

    def __init__(self, store: MindscapeStore, default_locale: str = "en"):
        self.store = store
        self.default_locale = default_locale
        self.intent_tags_store = IntentTagsStore()
        self.timeline_items_store = PostgresTimelineItemsStore()
        self.events_store = PostgresEventsStore()

    async def analyze_turn(
        self,
        workspace_id: str,
        profile_id: str,
        turn_id: str,
        conversation_id: Optional[str] = None,
    ) -> IntentLayoutPlan:
        return await analyze_turn(
            self,
            workspace_id=workspace_id,
            profile_id=profile_id,
            turn_id=turn_id,
            conversation_id=conversation_id,
        )

    async def _collect_input_data(
        self, workspace_id: str, profile_id: str, turn_id: str
    ) -> IntentStewardInput:
        return await collect_input_data(
            self,
            workspace_id=workspace_id,
            profile_id=profile_id,
            turn_id=turn_id,
        )

    async def prefilter_signals(
        self, signals: List[IntentSignal]
    ) -> List[IntentSignal]:
        return await prefilter_signals(self, signals)

    async def steward_analyze(
        self,
        filtered_signals: Optional[List[IntentSignal]] = None,
        context: Optional[IntentStewardInput] = None,
        **kwargs: Any,
    ) -> IntentLayoutPlan:
        return await steward_analyze_helper(
            self,
            filtered_signals=filtered_signals,
            context=context,
            **kwargs,
        )

    async def _llm_analyze_signals(
        self, filtered_signals: List[IntentSignal], context: IntentStewardInput
    ) -> Optional[IntentLayoutPlan]:
        return await llm_analyze_signals(self, filtered_signals, context)

    def _find_similar_intent(
        self, label: str, existing_intents: List[IntentCard]
    ) -> Optional[IntentCard]:
        return find_similar_intent(label, existing_intents)

    async def _check_auto_layout_flag(self, profile_id: str, workspace_id: str) -> bool:
        return await check_auto_layout_flag(
            self,
            profile_id=profile_id,
            workspace_id=workspace_id,
        )

    async def _execute_layout_plan(
        self,
        layout_plan: IntentLayoutPlan,
        workspace_id: str,
        profile_id: str,
        turn_id: str,
    ) -> None:
        await execute_layout_plan(
            self,
            layout_plan=layout_plan,
            workspace_id=workspace_id,
            profile_id=profile_id,
            turn_id=turn_id,
        )

    async def _write_analysis_log(
        self,
        layout_plan: IntentLayoutPlan,
        workspace_id: str,
        profile_id: str,
        turn_id: str,
    ) -> None:
        await write_analysis_log(
            self,
            layout_plan=layout_plan,
            workspace_id=workspace_id,
            profile_id=profile_id,
            turn_id=turn_id,
        )
