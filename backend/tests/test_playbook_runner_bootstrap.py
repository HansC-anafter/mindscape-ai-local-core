import os
import sys
from types import SimpleNamespace

import pytest

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from backend.app.services.playbook_runner_core.bootstrap import (
    load_playbook_bundle,
    resolve_locale,
    resolve_project_execution_context,
    resolve_variant,
)


@pytest.mark.asyncio
async def test_resolve_locale_prefers_inputs_then_workspace_then_default() -> None:
    assert (
        await resolve_locale(
            inputs={"locale": "en-US"},
            workspace_id="ws-1",
            get_workspace_fn=lambda workspace_id: _return_async(
                SimpleNamespace(default_locale="zh-TW")
            ),
        )
        == "en-US"
    )
    assert (
        await resolve_locale(
            inputs={},
            workspace_id="ws-1",
            get_workspace_fn=lambda workspace_id: _return_async(
                SimpleNamespace(default_locale="ja-JP")
            ),
        )
        == "ja-JP"
    )
    assert (
        await resolve_locale(
            inputs={},
            workspace_id=None,
            get_workspace_fn=lambda workspace_id: _return_async(None),
        )
        == "zh-TW"
    )


@pytest.mark.asyncio
async def test_load_playbook_bundle_returns_locale_and_total_steps() -> None:
    playbook, playbook_json, locale, total_steps = await load_playbook_bundle(
        playbook_code="demo_playbook",
        workspace_id="ws-1",
        inputs={},
        get_workspace_fn=lambda workspace_id: _return_async(
            SimpleNamespace(default_locale="zh-TW")
        ),
        get_playbook_fn=lambda **kwargs: _return_async(
            SimpleNamespace(metadata=SimpleNamespace(name="Demo"))
        ),
        load_playbook_json_fn=lambda playbook_code: SimpleNamespace(
            steps=[{"id": "one"}, {"id": "two"}]
        ),
    )

    assert playbook.metadata.name == "Demo"
    assert locale == "zh-TW"
    assert total_steps == 2
    assert len(playbook_json.steps) == 2


def test_resolve_variant_returns_none_when_missing() -> None:
    registry = SimpleNamespace(get_variant=lambda playbook_code, variant_id: None)

    variant = resolve_variant(
        registry=registry,
        playbook_code="demo_playbook",
        variant_id="v-1",
    )

    assert variant is None


@pytest.mark.asyncio
async def test_resolve_project_execution_context_uses_unified_sandbox() -> None:
    context = await resolve_project_execution_context(
        project_id="proj-1",
        inputs={},
        workspace_id="ws-1",
        get_project_fn=lambda **kwargs: _return_async({"id": kwargs["project_id"]}),
        get_unified_sandbox_fn=lambda **kwargs: _return_async(
            ("sbx-1", "/tmp/project")
        ),
        get_legacy_sandbox_path_fn=lambda **kwargs: _return_async("/tmp/legacy"),
    )

    assert context == {
        "project_id": "proj-1",
        "project_obj": {"id": "proj-1"},
        "project_sandbox_path": "/tmp/project",
        "sandbox_id": "sbx-1",
    }


@pytest.mark.asyncio
async def test_resolve_project_execution_context_can_lift_project_id_from_inputs() -> None:
    context = await resolve_project_execution_context(
        project_id=None,
        inputs={"project_id": "proj-2"},
        workspace_id="ws-1",
        get_project_fn=lambda **kwargs: _return_async({"id": kwargs["project_id"]}),
        get_unified_sandbox_fn=lambda **kwargs: _return_async(
            ("sbx-2", "/tmp/project-2")
        ),
        get_legacy_sandbox_path_fn=lambda **kwargs: _return_async("/tmp/legacy"),
    )

    assert context["project_id"] == "proj-2"
    assert context["sandbox_id"] == "sbx-2"


async def _return_async(value):
    return value
