from types import SimpleNamespace

import pytest

from backend.app.services.workflow.playbook_runtime import ensure_execution_sandbox
from backend.app.services.workflow.sandbox_admission import (
    resolve_execution_sandbox_admission,
)


def _browser_playbook(*, inputs=None, browser_contexts=1):
    return SimpleNamespace(
        playbook_code="browser_capture",
        inputs=inputs or {},
        execution_profile={
            "resource_class": "browser",
            "resource_requirements": {"browser_contexts": browser_contexts},
        },
    )


def test_dedicated_browser_workflow_without_project_contract_skips_sandbox() -> None:
    admission = resolve_execution_sandbox_admission(
        playbook_json=_browser_playbook(inputs={"workspace_id": object()}),
    )

    assert admission.required is False
    assert admission.reason == "dedicated_browser_context_without_project_contract"


@pytest.mark.asyncio
async def test_skipped_sandbox_does_not_touch_project_or_execution_factories() -> None:
    calls = []

    async def unexpected_call(**kwargs):
        calls.append(kwargs)
        raise AssertionError("sandbox dependency must not be touched")

    sandbox_id = await ensure_execution_sandbox(
        store=object(),
        playbook_json=_browser_playbook(inputs={"workspace_id": object()}),
        execution_id="execution-1",
        workspace_id="workspace-1",
        project_id="ambient-project-1",
        resume_checkpoint=None,
        get_project_fn=unexpected_call,
        get_or_create_project_sandbox_fn=unexpected_call,
        create_execution_sandbox_fn=unexpected_call,
    )

    assert sandbox_id is None
    assert calls == []


@pytest.mark.asyncio
async def test_declared_project_contract_preserves_project_sandbox_path() -> None:
    calls = []

    async def get_project(**kwargs):
        calls.append(("project", kwargs))
        return object()

    async def get_project_sandbox(**kwargs):
        calls.append(("project_sandbox", kwargs))
        return "sandbox-1"

    async def unexpected_execution_sandbox(**kwargs):
        calls.append(("execution_sandbox", kwargs))
        raise AssertionError("project sandbox must be reused")

    sandbox_id = await ensure_execution_sandbox(
        store=object(),
        playbook_json=_browser_playbook(
            inputs={"workspace_id": object(), "project_id": object()}
        ),
        execution_id="execution-1",
        workspace_id="workspace-1",
        project_id="project-1",
        resume_checkpoint=None,
        get_project_fn=get_project,
        get_or_create_project_sandbox_fn=get_project_sandbox,
        create_execution_sandbox_fn=unexpected_execution_sandbox,
    )

    assert sandbox_id == "sandbox-1"
    assert [call[0] for call in calls] == ["project", "project_sandbox"]


@pytest.mark.parametrize(
    "playbook_json",
    [
        SimpleNamespace(playbook_code="legacy", inputs={}, execution_profile=None),
        _browser_playbook(inputs={}, browser_contexts=0),
        SimpleNamespace(
            playbook_code="compute",
            inputs={},
            execution_profile={
                "resource_class": "compute",
                "resource_requirements": {"browser_contexts": 1},
            },
        ),
    ],
)
def test_incomplete_or_non_browser_contracts_preserve_default_sandbox(
    playbook_json,
) -> None:
    admission = resolve_execution_sandbox_admission(playbook_json=playbook_json)

    assert admission.required is True
    assert admission.reason == "default_repository_sandbox_contract"
