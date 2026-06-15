from datetime import timezone

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.mindscape_store_entity_tag_methods import (
    MindscapeStoreEntityTagMixin,
)
from backend.app.services.mindscape_store_event_methods import MindscapeStoreEventMixin
from backend.app.services.mindscape_store_execution_methods import (
    MindscapeStoreAgentExecutionMixin,
)
from backend.app.services.mindscape_store_intent_log_methods import (
    MindscapeStoreIntentLogMixin,
)
from backend.app.services.mindscape_store_intent_methods import MindscapeStoreIntentMixin
from backend.app.services.mindscape_store_profile_methods import MindscapeStoreProfileMixin
from backend.app.services.mindscape_store_utils import _utc_now
from backend.app.services.mindscape_store_workspace_project_methods import (
    MindscapeStoreWorkspaceProjectMixin,
)


def test_mindscape_store_facade_keeps_domain_mixins():
    assert MindscapeStore.__mro__[1:8] == (
        MindscapeStoreProfileMixin,
        MindscapeStoreIntentMixin,
        MindscapeStoreAgentExecutionMixin,
        MindscapeStoreEventMixin,
        MindscapeStoreIntentLogMixin,
        MindscapeStoreEntityTagMixin,
        MindscapeStoreWorkspaceProjectMixin,
    )


def test_mindscape_store_facade_exports_legacy_methods():
    expected = {
        "create_profile": "MindscapeStoreProfileMixin.create_profile",
        "create_intent": "MindscapeStoreIntentMixin.create_intent",
        "create_agent_execution": (
            "MindscapeStoreAgentExecutionMixin.create_agent_execution"
        ),
        "create_event": "MindscapeStoreEventMixin.create_event",
        "create_intent_log": "MindscapeStoreIntentLogMixin.create_intent_log",
        "create_entity": "MindscapeStoreEntityTagMixin.create_entity",
        "create_workspace": "MindscapeStoreWorkspaceProjectMixin.create_workspace",
        "list_projects": "MindscapeStoreWorkspaceProjectMixin.list_projects",
    }

    for method_name, qualname in expected.items():
        assert getattr(MindscapeStore, method_name).__qualname__ == qualname


def test_mindscape_store_utc_now_helper_is_timezone_aware():
    assert _utc_now().tzinfo is timezone.utc
