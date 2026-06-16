"""Task executor subprocess bootstrap helpers."""

import asyncio
import json
import logging
import os
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.app.services.playbook_run_executor import PlaybookRunExecutor

logger = logging.getLogger(__name__)


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

    task_type = payload.get("task_type", "playbook_execution")
    playbook_code = payload.get("playbook_code")
    profile_id = payload.get("profile_id")
    inputs = payload.get("inputs")
    workspace_id = payload.get("workspace_id")
    project_id = payload.get("project_id")
    result_file = payload.get("_result_file")

    async def _run() -> None:
        if task_type == "tool_execution":
            tool_name = payload.get("tool_name") or playbook_code
            from backend.app.services.unified_tool_executor import (
                UnifiedToolExecutor,
            )

            executor = UnifiedToolExecutor()
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
            await executor.execute_playbook_run(
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
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
