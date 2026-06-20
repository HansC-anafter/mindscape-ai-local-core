from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.services.playbook_output_artifact_creator as artifact_module
from backend.app.services.playbook_output_artifact_creator import (
    PlaybookOutputArtifactCreator,
    _serialize_artifact_file_content,
)


@pytest.mark.asyncio
async def test_write_artifact_to_file_delegates_to_single_helper(monkeypatch):
    calls = []

    async def fake_write_helper(
        creator,
        *,
        artifact,
        artifact_def,
        context,
        workspace_id,
        execution_context=None,
        playbook_metadata=None,
    ):
        calls.append(
            {
                "creator": creator,
                "artifact": artifact,
                "artifact_def": artifact_def,
                "context": context,
                "workspace_id": workspace_id,
                "execution_context": execution_context,
                "playbook_metadata": playbook_metadata,
            }
        )

    monkeypatch.setattr(
        artifact_module,
        "write_artifact_to_file_for_creator",
        fake_write_helper,
    )

    creator = PlaybookOutputArtifactCreator(artifacts_store=object())
    artifact = SimpleNamespace(id="artifact_1", title="Demo")
    artifact_def = {"file_write": {"enabled": True}}
    context = {"execution_id": "exec_1"}
    execution_context = {"sandbox_id": "sandbox_1"}
    playbook_metadata = {"playbook_code": "playbook_1"}

    await creator._write_artifact_to_file(
        artifact=artifact,
        artifact_def=artifact_def,
        context=context,
        workspace_id="workspace_1",
        execution_context=execution_context,
        playbook_metadata=playbook_metadata,
    )

    assert calls == [
        {
            "creator": creator,
            "artifact": artifact,
            "artifact_def": artifact_def,
            "context": context,
            "workspace_id": "workspace_1",
            "execution_context": execution_context,
            "playbook_metadata": playbook_metadata,
        }
    ]


@pytest.mark.asyncio
async def test_resolve_storage_path_delegates_to_single_helper(monkeypatch):
    calls = []
    expected_result = {
        "base_directory": Path("/tmp/workspace"),
        "relative_path": "artifacts/demo/file.txt",
    }

    async def fake_resolve_helper(**kwargs):
        calls.append(kwargs)
        return expected_result

    monkeypatch.setattr(
        artifact_module,
        "resolve_storage_path_for_creator",
        fake_resolve_helper,
    )

    creator = PlaybookOutputArtifactCreator(artifacts_store=object())
    result = await creator._resolve_storage_path(
        playbook_code="playbook_1",
        playbook_scope="workspace",
        execution_id="exec_1",
        artifact_file_name="{{title}}.txt",
        workspace_id="workspace_1",
        context={"title": "Demo"},
    )

    assert result == expected_result
    assert calls == [
        {
            "playbook_code": "playbook_1",
            "playbook_scope": "workspace",
            "execution_id": "exec_1",
            "artifact_file_name": "{{title}}.txt",
            "workspace_id": "workspace_1",
            "context": {"title": "Demo"},
        }
    ]


def test_get_or_register_filesystem_tool_delegates_to_single_helper(monkeypatch):
    calls = []

    def fake_register_helper(base_directory, playbook_scope, workspace_id):
        calls.append((base_directory, playbook_scope, workspace_id))
        return "filesystem_write_workspace_workspace_1"

    monkeypatch.setattr(
        artifact_module,
        "get_or_register_filesystem_tool_for_creator",
        fake_register_helper,
    )

    creator = PlaybookOutputArtifactCreator(artifacts_store=object())
    base_directory = Path("/tmp/workspace")

    tool_id = creator._get_or_register_filesystem_tool(
        base_directory,
        "workspace",
        "workspace_1",
    )

    assert tool_id == "filesystem_write_workspace_workspace_1"
    assert calls == [(base_directory, "workspace", "workspace_1")]


def test_serialize_artifact_file_content_stays_reexported_from_facade():
    assert _serialize_artifact_file_content({"content": "plain text"}) == "plain text"
