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

from backend.app.services.playbook_runner_core.session_state import (
    cleanup_execution,
    get_playbook_execution_result,
    get_or_restore_conversation_manager,
    list_active_execution_ids,
    preserve_sandbox_id_in_execution_context,
)


@pytest.mark.asyncio
async def test_get_or_restore_conversation_manager_prefers_memory() -> None:
    conv_manager = SimpleNamespace(execution_id="exec-1")
    active_conversations = {"exec-1": conv_manager}

    restored = await get_or_restore_conversation_manager(
        execution_id="exec-1",
        active_conversations=active_conversations,
        restore_execution_state_fn=_unexpected_restore,
    )

    assert restored is conv_manager


@pytest.mark.asyncio
async def test_get_or_restore_conversation_manager_restores_when_missing() -> None:
    active_conversations = {}
    restored = SimpleNamespace(execution_id="exec-2")

    conv_manager = await get_or_restore_conversation_manager(
        execution_id="exec-2",
        active_conversations=active_conversations,
        restore_execution_state_fn=lambda execution_id: _return_async(restored),
    )

    assert conv_manager is restored
    assert active_conversations["exec-2"] is restored


def test_preserve_sandbox_id_in_execution_context_updates_task() -> None:
    task = SimpleNamespace(id="task-1", execution_context={"x": 1})
    updates = []

    updated = preserve_sandbox_id_in_execution_context(
        execution_id="exec-1",
        sandbox_id="sbx-1",
        get_task_by_execution_id_fn=lambda execution_id: task,
        update_task_fn=lambda task_id, execution_context: updates.append(
            (task_id, execution_context)
        ),
    )

    assert updated is True
    assert updates == [("task-1", {"x": 1, "sandbox_id": "sbx-1"})]


def test_session_state_result_helpers_cover_active_and_completed_cases() -> None:
    active_conversations = {
        "exec-1": SimpleNamespace(extracted_data={"summary": "ok"}),
        "exec-2": SimpleNamespace(extracted_data=None),
    }

    assert get_playbook_execution_result(
        execution_id="exec-1",
        active_conversations=active_conversations,
    ) == {"summary": "ok"}
    assert (
        get_playbook_execution_result(
            execution_id="exec-2",
            active_conversations=active_conversations,
        )
        is None
    )
    assert get_playbook_execution_result(
        execution_id="exec-3",
        active_conversations=active_conversations,
    )["status"] == "completed"


def test_session_state_cleanup_and_listing() -> None:
    active_conversations = {
        "exec-1": SimpleNamespace(),
        "exec-2": SimpleNamespace(),
    }

    cleanup_execution(
        execution_id="exec-1",
        active_conversations=active_conversations,
    )

    assert list_active_execution_ids(active_conversations) == ["exec-2"]


async def _unexpected_restore(execution_id: str):
    raise AssertionError("restore_execution_state_fn should not be called")


async def _return_async(value):
    return value
