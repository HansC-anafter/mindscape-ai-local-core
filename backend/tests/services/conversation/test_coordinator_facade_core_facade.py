import asyncio

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.workspace import SideEffectLevel
from backend.app.services.conversation.coordinator_facade import CoordinatorFacade


class FakePlanBuilder:
    def __init__(self, side_effect_level):
        self.side_effect_level = side_effect_level

    def determine_side_effect_level(self, playbook_code):
        return self.side_effect_level


class FakeSuggestionCardCreator:
    def __init__(self):
        self.calls = []

    async def create_playbook_suggestion(
        self,
        playbook_code,
        playbook_context,
        workspace_id,
        message_id,
        event_emitter,
    ):
        self.calls.append(
            {
                "playbook_code": playbook_code,
                "playbook_context": playbook_context,
                "workspace_id": workspace_id,
                "message_id": message_id,
                "event_emitter": event_emitter,
            }
        )
        return {"task_id": "task-suggestion"}


def test_coordinator_facade_preserves_method_surface():
    required = [
        "execute_plan",
        "execute_plan_with_ctx",
        "_resolve_mind_lens",
        "_execute_readonly_task",
        "execute_playbook",
        "create_execution_with_ctx",
        "_execute_readonly_playbook",
    ]

    assert [name for name in required if not hasattr(CoordinatorFacade, name)] == []


def test_execute_plan_builds_local_context_before_delegation():
    facade = CoordinatorFacade.__new__(CoordinatorFacade)
    calls = []

    async def execute_plan_with_ctx_stub(**kwargs):
        calls.append(kwargs)
        return {"status": "delegated", "workspace_id": kwargs["ctx"].workspace_id}

    facade.execute_plan_with_ctx = execute_plan_with_ctx_stub

    result = asyncio.run(
        CoordinatorFacade.execute_plan(
            facade,
            execution_plan=object(),
            workspace_id="ws-1",
            profile_id="profile-1",
            message_id="msg-1",
            files=["file-1"],
            message="run",
            project_id="project-1",
        )
    )

    assert result == {"status": "delegated", "workspace_id": "ws-1"}
    assert calls[0]["ctx"].workspace_id == "ws-1"
    assert calls[0]["ctx"].actor_id == "profile-1"
    assert calls[0]["message_id"] == "msg-1"
    assert calls[0]["files"] == ["file-1"]
    assert calls[0]["project_id"] == "project-1"


def test_create_execution_with_ctx_preserves_suggestion_path():
    facade = CoordinatorFacade.__new__(CoordinatorFacade)
    facade.plan_builder = FakePlanBuilder(SideEffectLevel.SOFT_WRITE)
    facade.suggestion_card_creator = FakeSuggestionCardCreator()
    ctx = LocalDomainContext(
        actor_id="profile-1",
        workspace_id="ws-1",
        tags={"mode": "local"},
    )

    result = asyncio.run(
        CoordinatorFacade.create_execution_with_ctx(
            facade,
            playbook_code="planning",
            playbook_context={"topic": "roadmap"},
            ctx=ctx,
            message_id="msg-1",
        )
    )

    assert result == {"status": "suggestion", "task_id": "task-suggestion"}
    assert facade.suggestion_card_creator.calls[0]["playbook_code"] == "planning"
    assert facade.suggestion_card_creator.calls[0]["workspace_id"] == "ws-1"
    assert facade.suggestion_card_creator.calls[0]["message_id"] == "msg-1"
