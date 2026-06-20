from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.services.playbook_run_executor import (
    PlaybookRunExecutor,
    _runtime_result_has_errors,
    _workflow_result_has_errors,
)


def _playbook_run(inputs):
    return SimpleNamespace(playbook_json=SimpleNamespace(inputs=inputs))


def test_facade_result_status_helpers_preserve_nested_failure_detection():
    assert (
        _workflow_result_has_errors(
            {
                "status": "completed",
                "steps": {
                    "compose": {
                        "status": "completed",
                        "outputs": {"analysis_status": "failed"},
                    }
                },
            }
        )
        is True
    )

    runtime_result = SimpleNamespace(
        status="completed",
        metadata={"steps": {"render": {"status": "error", "error": "failed"}}},
    )
    assert _runtime_result_has_errors(runtime_result, {"status": "completed"}) is True


def test_facade_input_contract_preserves_mutable_default_copy():
    playbook_run = _playbook_run(
        {
            "workspace_id": {"required": True, "default": None},
            "target_handle": {"required": True, "default": None},
            "filters": {"required": False, "default": {"mode": "all"}},
        }
    )

    first = PlaybookRunExecutor._apply_playbook_input_contract(
        "demo",
        playbook_run,
        {"workspace_id": "ws-1", "target_handle": "target"},
    )
    second = PlaybookRunExecutor._apply_playbook_input_contract(
        "demo",
        playbook_run,
        {"workspace_id": "ws-1", "target_handle": "target"},
    )
    first["filters"]["mode"] = "changed"

    assert second["filters"] == {"mode": "all"}


@pytest.mark.asyncio
async def test_facade_remote_dispatch_releases_acquired_backend_once():
    executor = object.__new__(PlaybookRunExecutor)
    captured = {}
    release_backend = Mock()

    async def dispatch_remote_execution(**kwargs):
        captured.update(kwargs)
        return {"execution_mode": "remote", "execution_id": "exec-1"}

    executor._get_execution_dispatch_helpers = Mock(
        return_value=(
            dispatch_remote_execution,
            Mock(return_value=("remote", "remote")),
            release_backend,
        )
    )

    result = await executor._maybe_dispatch_remote_execution(
        playbook_code="demo_playbook",
        profile_id="profile-1",
        normalized_inputs={
            "execution_backend": "remote",
            "tenant_id": "tenant-1",
            "execution_id": "exec-1",
            "trace_id": "trace-1",
            "remote_job_type": "tool",
            "remote_capability_code": "ig",
            "remote_request_payload": {"tool_name": "ig.batch_vision"},
        },
        workspace_id="ws-1",
        project_id="proj-1",
    )

    assert result == {"execution_mode": "remote", "execution_id": "exec-1"}
    assert captured["playbook_code"] == "demo_playbook"
    assert captured["workspace_id"] == "ws-1"
    assert captured["project_id"] == "proj-1"
    assert captured["tenant_id"] == "tenant-1"
    assert captured["execution_id"] == "exec-1"
    assert captured["trace_id"] == "trace-1"
    assert captured["remote_job_type"] == "tool"
    assert captured["capability_code"] == "ig"
    assert captured["remote_request_payload"] == {"tool_name": "ig.batch_vision"}
    release_backend.assert_called_once_with("remote")


def test_source_boundaries_do_not_add_resource_or_duplicate_paths():
    backend_root = Path(__file__).resolve().parents[1]
    source_files = [
        backend_root / "app/services/playbook_run_executor.py",
        backend_root / "app/services/playbook_run_executor_core/result_status.py",
        backend_root / "app/services/playbook_run_executor_core/input_contract.py",
        backend_root / "app/services/playbook_run_executor_core/remote_execution.py",
        backend_root / "app/services/playbook_run_executor_core/runtime_provider_loading.py",
    ]
    combined = "\n".join(path.read_text() for path in source_files)

    forbidden_terms = [
        "APIRouter",
        "router.",
        "include_router",
        "Session(",
        "get_db",
        "commit(",
        "rollback(",
        "PgBouncer",
        "Queue",
        "Thread(",
        "Process(",
        "setInterval",
        "setTimeout",
    ]
    for term in forbidden_terms:
        assert term not in combined

    assert combined.count("class PlaybookRunExecutor") == 1
    assert "resolve_and_acquire_backend" in combined
    assert "release_backend" in combined
    assert "CapabilityRuntimeLoader" in combined
