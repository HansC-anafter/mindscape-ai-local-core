import os
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
sys.path.insert(0, os.path.abspath(_REPO_ROOT))
sys.path.insert(0, os.path.abspath(os.path.join(_REPO_ROOT, "backend")))


def make_engine_stub(**overrides: Any) -> Any:
    """Build a minimal MeetingEngine-shaped object for method testing."""
    from backend.app.services.orchestration.meeting.engine import MeetingEngine

    session = MagicMock()
    session.id = overrides.get("session_id", "test-session")
    session.workspace_id = overrides.get("workspace_id", "ws-test")
    session.agenda = overrides.get("agenda", ["single item"])

    store = MagicMock()
    store.update = MagicMock()

    engine = object.__new__(MeetingEngine)
    engine.session = session
    engine.session_store = store
    engine.model_name = overrides.get("model_name", "test-model")
    engine.executor_runtime = overrides.get("executor_runtime")
    engine._rag_tool_cache = overrides.get("rag_cache", [])
    engine._has_workspace_tool_bindings = MagicMock(
        return_value=overrides.get("has_bindings", False)
    )
    engine._verb_augment = MagicMock(return_value="search find")
    engine._build_action_items = AsyncMock(
        return_value=overrides.get("retry_items", [])
    )
    return engine
