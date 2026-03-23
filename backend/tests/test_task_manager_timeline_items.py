import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.models.workspace import SideEffectLevel, TimelineItemType
from backend.app.services.conversation.task_manager_core.timeline_items import (
    build_timeline_cta,
    create_failed_execution_timeline_item,
    create_task_completion_timeline_item,
    create_timeout_timeline_item,
    resolve_timeline_item_type,
)


class FakeI18n:
    def t(self, namespace, key, default=None, **kwargs):
        assert namespace == "conversation_orchestrator"
        if key == "suggestion.cta_add":
            return "Add"
        if key == "confirmation.button_confirm":
            return "Confirm"
        if default is not None:
            return default
        return f"{key}:{kwargs}"


def _task(**overrides):
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        workspace_id="ws-1",
        message_id="msg-1",
        pack_id="daily_planning",
        **overrides,
    )


def test_resolve_timeline_item_type_prefers_domain_and_error():
    assert (
        resolve_timeline_item_type("semantic_seeds", {})
        == TimelineItemType.INTENT_SEEDS
    )
    assert (
        resolve_timeline_item_type("whatever", {"error": "boom"})
        == TimelineItemType.ERROR
    )


def test_build_timeline_cta_for_soft_write_plan():
    cta = build_timeline_cta(
        playbook_code="task_planning",
        execution_result={},
        side_effect_level=SideEffectLevel.SOFT_WRITE,
        i18n=FakeI18n(),
    )

    assert cta == [
        {"label": "Add", "action": "add_to_tasks"},
        {"label": "View Plan", "action": "view_result"},
    ]


def test_create_task_completion_timeline_item_preserves_execution_result():
    execution_result = {"title": "Plan Ready", "summary": "A structured plan"}
    created_at = datetime.now(timezone.utc)
    item = create_task_completion_timeline_item(
        task=_task(),
        execution_result=execution_result,
        playbook_code="planning",
        side_effect_level=SideEffectLevel.READONLY,
        i18n=FakeI18n(),
        utc_now_fn=lambda: created_at,
    )

    assert item.type == TimelineItemType.PLAN
    assert item.data == execution_result
    assert item.cta == [{"label": "View Plan", "action": "view_result"}]
    assert item.created_at == created_at


def test_error_timeline_item_builders_share_expected_shape():
    task = _task()
    failed_created_at = datetime.now(timezone.utc)
    timeout_created_at = datetime.now(timezone.utc)
    failed_item = create_failed_execution_timeline_item(
        task=task,
        playbook_code="broken_pack",
        error_message="Execution completed but no result available",
        utc_now_fn=lambda: failed_created_at,
    )
    timeout_item = create_timeout_timeline_item(
        task=task,
        timeout_error="Task timed out after 5 minutes",
        timeout_minutes=5,
        i18n=FakeI18n(),
        utc_now_fn=lambda: timeout_created_at,
    )

    assert failed_item.type == TimelineItemType.ERROR
    assert failed_item.summary == "Execution completed but no result available"
    assert failed_item.created_at == failed_created_at
    assert timeout_item.type == TimelineItemType.ERROR
    assert timeout_item.data["timeout_minutes"] == 5
    assert timeout_item.created_at == timeout_created_at
