"""Subprocess helpers for runner task execution."""

import asyncio
import logging
import os
import tempfile
from typing import Any, Callable, Dict, Optional

from backend.app.models.workspace import Task

logger = logging.getLogger(__name__)


def create_result_file(task_id: str) -> str:
    result_fd, result_file = tempfile.mkstemp(
        prefix=f"runner_result_{task_id}_", suffix=".json"
    )
    os.close(result_fd)
    return result_file


def build_child_payload(
    *,
    task: Task,
    runner_id: str,
    inputs: Dict[str, Any],
    ctx: Dict[str, Any],
    resolved_profile_id: str,
    result_file: str,
) -> Dict[str, Any]:
    return {
        "runner_id": runner_id,
        "task_id": task.id,
        "playbook_code": task.pack_id,
        "task_type": task.task_type or "playbook_execution",
        "tool_name": (ctx.get("tool_name") if isinstance(ctx, dict) else None),
        "profile_id": resolved_profile_id,
        "inputs": inputs,
        "workspace_id": task.workspace_id,
        "project_id": task.project_id,
        "root_execution_id": task.execution_id or task.id,
        "execution_admission_snapshot": (
            ctx.get("execution_admission_snapshot")
            if isinstance(ctx, dict)
            else None
        ),
        "_result_file": result_file,
    }


def start_child_process(
    *,
    ctx_mp: Any,
    target: Callable[[Dict[str, Any]], None],
    payload: Dict[str, Any],
    task: Task,
    trace_heartbeat: bool,
) -> Any:
    proc = ctx_mp.Process(target=target, args=(payload,), daemon=True)
    logger.info(
        "Runner subprocess starting task_id=%s playbook=%s",
        task.id,
        task.pack_id,
    )
    try:
        proc.start()
    except BaseException as start_exc:
        logger.exception(
            "Runner subprocess start failed task_id=%s playbook=%s: %s",
            task.id,
            task.pack_id,
            start_exc,
        )
        raise
    if trace_heartbeat:
        logger.warning(
            "Runner subprocess started task_id=%s playbook=%s pid=%s",
            task.id,
            task.pack_id,
            proc.pid,
        )
    else:
        logger.info(
            "Runner subprocess started task_id=%s playbook=%s pid=%s",
            task.id,
            task.pack_id,
            proc.pid,
        )
    return proc


async def wait_for_process_exit(
    *,
    proc: Any,
    task: Task,
    trace_heartbeat: bool,
    asyncio_module: Any = asyncio,
) -> int:
    while proc.is_alive():
        await asyncio_module.sleep(0.5)
    exitcode: Optional[int] = proc.exitcode
    if trace_heartbeat:
        logger.warning(
            "Runner subprocess exited task_id=%s playbook=%s pid=%s exitcode=%s",
            task.id,
            task.pack_id,
            proc.pid,
            exitcode,
        )
    else:
        logger.info(
            "Runner subprocess exited task_id=%s playbook=%s pid=%s exitcode=%s",
            task.id,
            task.pack_id,
            proc.pid,
            exitcode,
        )
    if exitcode is None:
        logger.warning(
            f"Runner subprocess exitcode is None (zombie?) for task {task.id}"
        )
        return -1
    return int(exitcode)
