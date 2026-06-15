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
from backend.app.services.mindscape_store_workspace_project_methods import (
    MindscapeStoreWorkspaceProjectMixin,
)


def test_mindscape_store_facade_keeps_domain_mixins():
    mro = set(MindscapeStore.__mro__)

    assert MindscapeStoreProfileMixin in mro
    assert MindscapeStoreIntentMixin in mro
    assert MindscapeStoreAgentExecutionMixin in mro
    assert MindscapeStoreEventMixin in mro
    assert MindscapeStoreIntentLogMixin in mro
    assert MindscapeStoreEntityTagMixin in mro
    assert MindscapeStoreWorkspaceProjectMixin in mro


def test_mindscape_store_facade_exports_legacy_methods():
    assert hasattr(MindscapeStore, "create_profile")
    assert hasattr(MindscapeStore, "create_intent")
    assert hasattr(MindscapeStore, "create_agent_execution")
    assert hasattr(MindscapeStore, "create_event")
    assert hasattr(MindscapeStore, "create_intent_log")
    assert hasattr(MindscapeStore, "create_entity")
    assert hasattr(MindscapeStore, "create_workspace")
