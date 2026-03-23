from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.app.models.mindscape import IntentStatus, PriorityLevel
from backend.app.services.conversation.suggestion_action_handler_core.mindscape_actions import (
    build_empty_action_response,
    create_user_event,
    handle_add_to_mindscape,
    handle_create_intent,
    handle_error,
)


def test_build_empty_action_response_shape():
    assert build_empty_action_response("ws_123") == {
        "workspace_id": "ws_123",
        "display_events": [],
        "triggered_playbook": None,
        "pending_tasks": [],
    }


def test_create_user_event_writes_message_event():
    store = Mock()

    create_user_event(
        store=store,
        workspace_id="ws_123",
        profile_id="user_123",
        project_id="proj_123",
        message="Execute pack",
        action="execute_pack",
        action_params={"pack_id": "daily_planning"},
    )

    event = store.create_event.call_args.args[0]
    assert event.workspace_id == "ws_123"
    assert event.profile_id == "user_123"
    assert event.payload["action"] == "execute_pack"


def test_handle_create_intent_success():
    store = Mock()
    store.create_intent.side_effect = lambda intent: intent
    ctx = SimpleNamespace(actor_id="user_123", workspace_id="ws_123")

    response = handle_create_intent(
        store=store,
        default_locale="en",
        ctx=ctx,
        action_params={"title": "Ship Wave B", "description": "Finish modularization"},
        project_id="proj_123",
    )

    created_intent = store.create_intent.call_args.args[0]
    assert created_intent.title == "Ship Wave B"
    assert created_intent.status == IntentStatus.ACTIVE
    assert created_intent.priority == PriorityLevel.MEDIUM
    assert response["created_intent"]["title"] == "Ship Wave B"
    assert store.create_event.called


def test_handle_add_to_mindscape_creates_new_intents_and_timeline():
    store = Mock()
    store.list_intents.return_value = [SimpleNamespace(title="Existing")]
    ctx = SimpleNamespace(actor_id="user_123", workspace_id="ws_123")
    timeline_store = Mock()

    with patch(
        "backend.app.services.conversation.suggestion_action_handler_core.mindscape_actions.PostgresTimelineItemsStore",
        return_value=timeline_store,
    ):
        response = handle_add_to_mindscape(
            store=store,
            default_locale="en",
            ctx=ctx,
            action_params={
                "intents": ["Existing", {"title": "New Goal"}],
                "themes": ["focus"],
            },
            message_id="msg_123",
        )

    assert store.create_intent.call_count == 1
    created_intent = store.create_intent.call_args.args[0]
    assert created_intent.title == "New Goal"
    assert timeline_store.create_timeline_item.called
    assert response["message"].endswith("Added 1 intent(s).")


def test_handle_error_creates_system_event():
    store = Mock()

    response = handle_error(
        store=store,
        default_locale="en",
        workspace_id="ws_123",
        profile_id="user_123",
        project_id="proj_123",
        error_message="boom",
    )

    event = store.create_event.call_args.args[0]
    assert event.profile_id == "user_123"
    assert response["workspace_id"] == "ws_123"
