import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.models.playbook import PlaybookOwnerType, PlaybookVisibility
from backend.app.services.playbook_service import (
    ExecutionMode,
    ExecutionResult,
    PlaybookService,
)
from backend.app.services.playbook_service_execution import (
    resolve_project_id_for_execution,
)
from backend.app.services.playbook_service_metadata import (
    filter_playbooks_by_runtime_tier,
    metadata_to_dict,
)
from backend.app.services.playbook_service_models import (
    ExecutionMode as HelperExecutionMode,
    ExecutionResult as HelperExecutionResult,
)


def _metadata(**overrides):
    base = {
        "playbook_code": "pb-1",
        "version": "1.0",
        "name": "Playbook",
        "description": "Description",
        "tags": ["tag-a"],
        "kind": "workflow",
        "interaction_mode": ["chat"],
        "visible_in": ["library"],
        "owner_type": PlaybookOwnerType.WORKSPACE,
        "owner_id": "workspace-1",
        "visibility": PlaybookVisibility.WORKSPACE_SHARED,
        "capability_tags": ["cap-a"],
        "project_types": ["project-a"],
        "shared_with_workspaces": ["workspace-2"],
        "allowed_tools": ["tool-a"],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_legacy_public_facade_names_remain_importable() -> None:
    result = ExecutionResult("exec-1", "running", progress=0.5)

    assert issubclass(PlaybookService, object)
    assert ExecutionMode is HelperExecutionMode
    assert ExecutionResult is HelperExecutionResult
    assert ExecutionMode.ASYNC.value == "async"
    assert result.execution_id == "exec-1"
    assert result.status == "running"
    assert result.progress == 0.5


def test_runtime_tier_filtering_preserves_existing_rules() -> None:
    local = _metadata(playbook_code="local", runtime_tier="local")
    cloud_recommended = _metadata(
        playbook_code="cloud_recommended",
        runtime_tier="cloud_recommended",
    )
    cloud_only = _metadata(playbook_code="cloud_only", runtime_tier="cloud_only")
    playbooks = [local, cloud_recommended, cloud_only]

    assert filter_playbooks_by_runtime_tier(playbooks, None) == playbooks
    assert [pb.playbook_code for pb in filter_playbooks_by_runtime_tier(playbooks, "local")] == [
        "local",
        "cloud_recommended",
    ]
    assert [
        pb.playbook_code
        for pb in filter_playbooks_by_runtime_tier(playbooks, "cloud_recommended")
    ] == ["local", "cloud_recommended", "cloud_only"]
    assert [
        pb.playbook_code
        for pb in filter_playbooks_by_runtime_tier(playbooks, "cloud_only")
    ] == ["cloud_only"]


def test_metadata_to_dict_preserves_explicit_and_legacy_identity_fields() -> None:
    explicit = metadata_to_dict(_metadata())
    legacy = metadata_to_dict(
        SimpleNamespace(
            playbook_code="pb-legacy",
            version="1.0",
            name="Legacy",
            description="Description",
            tags=[],
            kind="workflow",
            interaction_mode=[],
            visible_in=[],
            scope={"visibility": "workspace"},
            owner={"workspace_id": "workspace-legacy"},
        )
    )

    assert explicit["owner_type"] == PlaybookOwnerType.WORKSPACE.value
    assert explicit["owner_id"] == "workspace-1"
    assert explicit["visibility"] == PlaybookVisibility.WORKSPACE_SHARED.value
    assert explicit["allowed_tools"] == ["tool-a"]
    assert legacy["owner_type"] == PlaybookOwnerType.WORKSPACE.value
    assert legacy["owner_id"] == "workspace-legacy"
    assert legacy["visibility"] == PlaybookVisibility.WORKSPACE_SHARED.value
    assert legacy["capability_tags"] == []


@pytest.mark.asyncio
async def test_project_id_resolution_preserves_precedence() -> None:
    calls = []

    class _Store:
        async def get_workspace(self, workspace_id):
            calls.append(workspace_id)
            return SimpleNamespace(primary_project_id="workspace-project")

    logger = logging.getLogger(__name__)
    assert await resolve_project_id_for_execution(
        store=_Store(),
        workspace_id="workspace-1",
        inputs={"project_id": "input-project"},
        explicit_project_id="explicit-project",
        playbook_code="pb-1",
        logger=logger,
    ) == "explicit-project"
    assert calls == []

    assert await resolve_project_id_for_execution(
        store=_Store(),
        workspace_id="workspace-1",
        inputs={"project_id": "input-project"},
        explicit_project_id=None,
        playbook_code="pb-1",
        logger=logger,
    ) == "input-project"
    assert calls == []

    assert await resolve_project_id_for_execution(
        store=_Store(),
        workspace_id="workspace-1",
        inputs={},
        explicit_project_id=None,
        playbook_code="pb-1",
        logger=logger,
    ) == "workspace-project"
    assert calls == ["workspace-1"]


def test_helper_modules_do_not_define_duplicate_resource_surfaces() -> None:
    root = Path("backend/app/services")
    source_files = {
        root / "playbook_service.py": "facade",
        root / "playbook_service_models.py": "models",
        root / "playbook_service_metadata.py": "metadata",
        root / "playbook_service_forking.py": "forking",
        root / "playbook_service_validation.py": "validation",
        root / "playbook_service_execution.py": "execution",
    }
    forbidden_markers = [
        "APIRouter",
        "@router",
        "create_engine",
        "sessionmaker",
        "PgBouncer",
        "pgbouncer",
        "asyncio.create_task",
        "setInterval",
    ]

    for source_file in source_files:
        source = source_file.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in source, f"{marker} found in {source_file}"
        if source_files[source_file] != "facade":
            assert "class PlaybookService" not in source

    execution_source = (root / "playbook_service_execution.py").read_text(
        encoding="utf-8"
    )
    non_execution_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path, role in source_files.items()
        if role != "execution"
    )
    assert "PlaybookRunExecutor" in execution_source
    assert "TasksStore" in execution_source
    assert "PlaybookRunExecutor" not in non_execution_sources
    assert "TasksStore" not in non_execution_sources
