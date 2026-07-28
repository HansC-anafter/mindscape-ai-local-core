"""Subprocess helpers for runner task execution."""

import asyncio
import logging
import os
import pickle
import subprocess
import sys
import tempfile
from typing import Any, Callable, Dict, Optional

from backend.app.models.workspace import Task

logger = logging.getLogger(__name__)


class RunnerChildProcess:
    """Expose the multiprocessing.Process lifecycle used by runner cleanup."""

    def __init__(self, process: subprocess.Popen[Any], payload_file: str):
        self._process = process
        self._payload_file = payload_file

    @property
    def pid(self) -> int:
        return int(self._process.pid)

    @property
    def exitcode(self) -> Optional[int]:
        exitcode = self._process.poll()
        if exitcode is not None:
            self._cleanup_payload_file()
        return exitcode

    def is_alive(self) -> bool:
        alive = self._process.poll() is None
        if not alive:
            self._cleanup_payload_file()
        return alive

    def join(self, timeout: Optional[float] = None) -> None:
        try:
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return
        self._cleanup_payload_file()

    def terminate(self) -> None:
        self._process.terminate()

    def kill(self) -> None:
        self._process.kill()

    def _cleanup_payload_file(self) -> None:
        if not self._payload_file:
            return
        try:
            os.unlink(self._payload_file)
        except FileNotFoundError:
            pass
        finally:
            self._payload_file = ""


def create_result_file(task_id: str) -> str:
    result_fd, result_file = tempfile.mkstemp(
        prefix=f"runner_result_{task_id}_", suffix=".json"
    )
    os.close(result_fd)
    return result_file


def create_child_payload_file(task_id: str, payload: Dict[str, Any]) -> str:
    payload_fd, payload_file = tempfile.mkstemp(
        prefix=f"runner_payload_{task_id}_",
        suffix=".pickle",
    )
    try:
        with os.fdopen(payload_fd, "wb") as file_obj:
            pickle.dump(payload, file_obj, protocol=pickle.HIGHEST_PROTOCOL)
    except BaseException:
        try:
            os.unlink(payload_file)
        except FileNotFoundError:
            pass
        raise
    return payload_file


def build_child_payload(
    *,
    task: Task,
    runner_id: str,
    inputs: Dict[str, Any],
    ctx: Dict[str, Any],
    resolved_profile_id: str,
    result_file: str,
) -> Dict[str, Any]:
    task_type = task.task_type or "playbook_execution"
    capability_code: Optional[str] = None
    if task_type != "tool_execution":
        from backend.app.services.runner_topology.spec_metadata import (
            resolve_installed_playbook_runner_metadata,
        )

        runner_metadata = resolve_installed_playbook_runner_metadata(
            str(task.pack_id or "").strip()
        )
        capability_code = str(
            (runner_metadata or {}).get("capability_code") or ""
        ).strip() or None
    child_inputs = dict(inputs)
    admission_snapshot = (
        ctx.get("execution_admission_snapshot")
        if isinstance(ctx, dict)
        else None
    )
    if isinstance(admission_snapshot, dict):
        child_inputs["execution_admission_snapshot"] = admission_snapshot
    internal_projection_admission = (
        ctx.get("knowledge_projection_admission")
        if isinstance(ctx, dict)
        else None
    )
    return {
        "runner_id": runner_id,
        "task_id": task.id,
        "playbook_code": task.pack_id,
        "task_type": task_type,
        "capability_code": capability_code,
        "tool_name": (ctx.get("tool_name") if isinstance(ctx, dict) else None),
        "profile_id": resolved_profile_id,
        "inputs": child_inputs,
        "workspace_id": task.workspace_id,
        "project_id": task.project_id,
        "root_execution_id": task.execution_id or task.id,
        "execution_admission_snapshot": admission_snapshot,
        "knowledge_projection_admission": internal_projection_admission,
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
    # Preserve the injected seam but avoid multiprocessing.spawn: spawn
    # re-imports the full runner entrypoint before resolving the child target.
    _ = (ctx_mp, target)
    payload_file = create_child_payload_file(task.id, payload)
    command = [
        sys.executable,
        "-u",
        "-m",
        "backend.app.runner.task_executor_child",
        "--payload-file",
        payload_file,
    ]
    logger.info(
        "Runner subprocess starting task_id=%s playbook=%s",
        task.id,
        task.pack_id,
    )
    try:
        child = subprocess.Popen(command, close_fds=True)
    except BaseException as start_exc:
        try:
            os.unlink(payload_file)
        except FileNotFoundError:
            pass
        logger.exception(
            "Runner subprocess start failed task_id=%s playbook=%s: %s",
            task.id,
            task.pack_id,
            start_exc,
        )
        raise
    proc = RunnerChildProcess(child, payload_file)
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
