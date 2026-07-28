"""Task executor subprocess bootstrap helpers."""

import asyncio
import json
import logging
import os
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.app.services.playbook_run_executor import PlaybookRunExecutor
from backend.app.services.workspace_capability_admission.child_snapshot_verifier import (
    verify_child_snapshot,
)

logger = logging.getLogger(__name__)


def _playbook_result_status(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    nested = payload.get("result")
    if isinstance(nested, dict) and nested.get("status") is not None:
        return str(nested.get("status") or "").strip().lower()
    return str(payload.get("status") or "").strip().lower()


def _write_result_file(result_file: Optional[str], payload: Any) -> None:
    if not result_file:
        return
    with open(result_file, "w") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, default=str)


def _initialize_capability_packages_for_runner(*, load_tools: bool = True) -> None:
    try:
        from backend.app.services.capability_registry import get_registry, load_capabilities

        app_dir = Path(__file__).resolve().parent.parent
        capabilities_dir = (app_dir / "capabilities").resolve()
        load_capabilities(capabilities_dir)
        if load_tools:
            from backend.app.services.capability_tool_loader import load_all_capability_tools

            load_all_capability_tools()

        registry = get_registry()
        logger.info(
            "Runner capability packages loaded: %s capabilities, %s tools, load_tools=%s",
            len(registry.list_capabilities()),
            len(registry.list_tools()),
            load_tools,
        )
    except Exception as e:
        logger.error(f"Runner failed to load capability packages: {e}", exc_info=True)


def _child_execute_playbook(
    payload: Dict[str, Any],
    *,
    initialize_capability_packages_for_runner: Callable[..., None],
) -> None:
    """
    Run a single playbook or tool execution inside a dedicated process.
    This isolates Playwright/driver hangs that may hold the GIL and would otherwise
    freeze runner heartbeats/lock renew threads.
    """
    os.environ["LOCAL_CORE_RUNNER_PROCESS"] = "1"
    runner_id = str(payload.get("runner_id") or "").strip()
    task_id = str(payload.get("task_id") or "").strip()
    if runner_id:
        os.environ["LOCAL_CORE_RUNNER_ID"] = runner_id
    if task_id:
        os.environ["LOCAL_CORE_TASK_ID"] = task_id
    workspace_id = payload.get("workspace_id")
    admission_snapshot = payload.get("execution_admission_snapshot")
    task_type = payload.get("task_type", "playbook_execution")
    playbook_code = payload.get("playbook_code")
    tool_name = payload.get("tool_name") or playbook_code
    internal_projection_admission = payload.get(
        "knowledge_projection_admission"
    )
    if workspace_id:
        from backend.app.services.knowledge_projection.retrievable.source_admission import (
            INTERNAL_PROJECTION_TOOL,
        )

        if tool_name == INTERNAL_PROJECTION_TOOL:
            from backend.app.services.knowledge_projection.retrievable.internal_admission import (
                InternalProjectionAdmissionReceipt,
            )

            receipt = InternalProjectionAdmissionReceipt.model_validate(
                internal_projection_admission
            )
            if (
                receipt.task_id != task_id
                or receipt.workspace_id != str(workspace_id)
            ):
                raise RuntimeError(
                    "runner_child_internal_projection_admission_mismatch"
                )
        else:
            if internal_projection_admission is not None:
                raise RuntimeError(
                    "runner_child_internal_projection_admission_forbidden"
                )
            if not isinstance(admission_snapshot, dict):
                raise RuntimeError("runner_child_admission_snapshot_required")
            verify_child_snapshot(
                admission_snapshot,
                expected_workspace_id=str(workspace_id),
                expected_root_execution_id=str(
                    payload.get("root_execution_id") or task_id
                ),
            )
    try:
        eager_tool_load = (
            os.getenv("LOCAL_CORE_RUNNER_CHILD_EAGER_TOOL_LOAD", "")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"}
        )
        initialize_capability_packages_for_runner(load_tools=eager_tool_load)
    except Exception:
        pass

    profile_id = payload.get("profile_id")
    inputs = payload.get("inputs")
    project_id = payload.get("project_id")
    result_file = payload.get("_result_file")

    async def _run() -> None:
        if task_type == "tool_execution":
            from backend.app.services.unified_tool_executor import (
                UnifiedToolExecutor,
            )

            executor = UnifiedToolExecutor()
            from backend.app.services.tools.internal_execution import (
                runner_internal_tool_authority,
            )

            snapshot_hash = str(
                (
                    internal_projection_admission
                    if tool_name == INTERNAL_PROJECTION_TOOL
                    else (admission_snapshot or {})
                ).get(
                    (
                        "receipt_hash"
                        if tool_name == INTERNAL_PROJECTION_TOOL
                        else "snapshot_hash"
                    )
                )
                or ""
            )
            with runner_internal_tool_authority(
                task_id=str(task_id),
                tool_name=str(tool_name),
                admission_snapshot_hash=snapshot_hash,
            ):
                result = await executor.execute_tool(
                    tool_name=tool_name,
                    arguments=inputs or {},
                )
            if not result.success:
                raise RuntimeError(
                    f"Tool execution failed for '{tool_name}': {result.error}"
                )
            if result_file:
                try:
                    with open(result_file, "w") as f:
                        json.dump(result.to_dict(), f)
                except Exception:
                    pass
        else:
            executor = PlaybookRunExecutor()
            if task_id:
                executor.playbook_runner.tool_executor.execution_context[
                    "task_id"
                ] = task_id
            result = await executor.execute_playbook_run(
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
            )
            _write_result_file(result_file, result)
            if _playbook_result_status(result) in {"error", "failed"}:
                detail = (
                    result.get("result", {}).get("error")
                    if isinstance(result.get("result"), dict)
                    else None
                )
                raise RuntimeError(
                    "Terminal workflow failure"
                    + (f": {detail}" if detail else "")
                )

    try:
        asyncio.run(_run())
    except Exception as e:
        if result_file:
            try:
                with open(result_file, "w") as f:
                    json.dump(
                        {
                            "status": "failed",
                            "error": str(e),
                            "exception_type": type(e).__name__,
                            "traceback": traceback.format_exc(),
                        },
                        f,
                    )
            except Exception:
                pass
        raise


def _build_subprocess_failure_message(
    result_file: Optional[str],
    exitcode: int,
) -> str:
    msg = f"Runner subprocess exited non-zero (exitcode={exitcode})"
    if not result_file or not os.path.exists(result_file):
        return msg
    try:
        with open(result_file, "r") as f:
            payload = json.load(f)
    except Exception:
        return msg

    if not isinstance(payload, dict):
        return msg

    detail = payload.get("error") or payload.get("message")
    if isinstance(detail, str) and detail.strip():
        return f"{msg}: {detail.strip()}"
    return msg
