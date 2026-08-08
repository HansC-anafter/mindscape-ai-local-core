"""Task executor subprocess bootstrap helpers."""

import asyncio
import json
import logging
import os
import pickle
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)
PlaybookRunExecutor: Any = None


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


def _initialize_capability_packages_for_runner(
    *,
    load_tools: bool = True,
    capability_code: Optional[str] = None,
) -> None:
    normalized_capability_code = str(capability_code or "").strip()
    try:
        from backend.app.services.capability_registry import (
            get_registry,
            load_capabilities,
            reload_capability,
        )

        app_dir = Path(__file__).resolve().parent.parent
        capabilities_dir = (app_dir / "capabilities").resolve()
        if normalized_capability_code:
            if not reload_capability(
                normalized_capability_code,
                capabilities_dir,
            ):
                raise RuntimeError(
                    "runner_child_capability_manifest_not_found:"
                    f"{normalized_capability_code}"
                )
        else:
            load_capabilities(capabilities_dir)
        if load_tools:
            from backend.app.services.capability_tool_loader import (
                load_all_capability_tools,
            )

            load_all_capability_tools()

        registry = get_registry()
        logger.info(
            "Runner capability packages loaded: %s capabilities, %s tools, "
            "load_tools=%s capability_code=%s",
            len(registry.list_capabilities()),
            len(registry.list_tools()),
            load_tools,
            normalized_capability_code or "all",
        )
    except Exception as e:
        logger.error(f"Runner failed to load capability packages: {e}", exc_info=True)
        if normalized_capability_code:
            raise


def _child_execute_playbook(
    payload: Dict[str, Any],
    *,
    initialize_capability_packages_for_runner: Optional[
        Callable[..., None]
    ] = None,
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
    capability_code = str(payload.get("capability_code") or "").strip()
    tool_name = payload.get("tool_name") or playbook_code
    internal_projection_admission = payload.get("knowledge_projection_admission")
    outcome_evaluation_admission = payload.get("product_outcome_evaluation_admission")
    outcome_runtime_trust = None
    if task_type == "product_outcome_evaluation" and not workspace_id:
        raise RuntimeError("runner_child_outcome_workspace_required")
    if workspace_id:
        from backend.app.services.knowledge_projection.retrievable.source_admission import (
            INTERNAL_PROJECTION_TOOL,
        )

        if task_type == "product_outcome_evaluation":
            from backend.app.services.workflow.durable_state.outcome_runtime_trust import (
                OutcomeRuntimeTrust,
            )
            from backend.app.services.workflow.durable_state.outcome_task_admission import (
                verify_outcome_task_admission,
            )

            if internal_projection_admission is not None:
                raise RuntimeError(
                    "runner_child_outcome_projection_admission_forbidden"
                )
            outcome_runtime_trust = OutcomeRuntimeTrust.from_mounted_files()
            verify_outcome_task_admission(
                outcome_evaluation_admission,
                expected_task_id=task_id,
                expected_workspace_id=str(workspace_id),
                expected_params=dict(inputs or {}),
                verification_keys=(
                    outcome_runtime_trust.descriptor_verification_keys
                ),
            )
        elif tool_name == INTERNAL_PROJECTION_TOOL:
            from backend.app.services.knowledge_projection.retrievable.internal_admission import (
                InternalProjectionAdmissionReceipt,
            )

            receipt = InternalProjectionAdmissionReceipt.model_validate(
                internal_projection_admission
            )
            if receipt.task_id != task_id or receipt.workspace_id != str(workspace_id):
                raise RuntimeError(
                    "runner_child_internal_projection_admission_mismatch"
                )
        else:
            from backend.app.services.workspace_capability_admission.child_snapshot_verifier import (
                verify_child_snapshot,
            )

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
    if task_type != "tool_execution" and not capability_code:
        raise RuntimeError("runner_child_capability_code_required")
    eager_tool_load = (
        os.getenv("LOCAL_CORE_RUNNER_CHILD_EAGER_TOOL_LOAD", "")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"}
    )
    initialize_packages = (
        initialize_capability_packages_for_runner
        or _initialize_capability_packages_for_runner
    )
    initialization_started = time.monotonic()
    try:
        initialize_packages(
            load_tools=eager_tool_load,
            capability_code=capability_code or None,
        )
    except Exception:
        if capability_code:
            raise
    logger.info(
        "Runner child capability initialization complete task_id=%s "
        "capability_code=%s elapsed_ms=%s",
        task_id,
        capability_code or "none",
        int((time.monotonic() - initialization_started) * 1000),
    )

    profile_id = payload.get("profile_id")
    inputs = payload.get("inputs")
    project_id = payload.get("project_id")
    result_file = payload.get("_result_file")

    async def _run_with_runtime_identity() -> None:
        if task_type == "product_outcome_evaluation":
            from backend.app.services.workflow.durable_state.outcome_task_dispatcher import (
                OutcomeTaskDispatcher,
            )

            if outcome_runtime_trust is None:
                raise RuntimeError("runner_child_outcome_trust_required")
            result = OutcomeTaskDispatcher().execute(
                task_id=task_id,
                workspace_id=str(workspace_id),
                capability_code=str(playbook_code),
                params=dict(inputs or {}),
                admission=dict(outcome_evaluation_admission or {}),
                trust=outcome_runtime_trust,
            )
            _write_result_file(result_file, result)
        elif task_type == "tool_execution":
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
            executor_type = PlaybookRunExecutor
            if executor_type is None:
                executor_import_started = time.monotonic()
                from backend.app.services.playbook_run_executor import (
                    PlaybookRunExecutor as executor_type,
                )

                logger.info(
                    "Runner child playbook executor import complete task_id=%s "
                    "elapsed_ms=%s",
                    task_id,
                    int((time.monotonic() - executor_import_started) * 1000),
                )
            executor = executor_type()
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
                    "Terminal workflow failure" + (f": {detail}" if detail else "")
                )

    async def _run() -> None:
        from backend.app.services.capability_tool_invocation import (
            runtime_task_identity_scope,
        )

        with runtime_task_identity_scope(task_id):
            await _run_with_runtime_identity()

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


def _read_child_payload_file(payload_file: str) -> Dict[str, Any]:
    try:
        with open(payload_file, "rb") as file_obj:
            payload = pickle.load(file_obj)
    finally:
        try:
            os.unlink(payload_file)
        except FileNotFoundError:
            pass
    if not isinstance(payload, dict):
        raise RuntimeError("runner_child_payload_must_be_mapping")
    return payload


def main(argv: Optional[list[str]] = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "--payload-file":
        raise RuntimeError("runner_child_payload_file_argument_required")
    payload = _read_child_payload_file(args[1])
    logger.info(
        "Runner lightweight child entry task_id=%s capability_code=%s",
        payload.get("task_id"),
        payload.get("capability_code"),
    )
    _child_execute_playbook(payload)


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


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    main()
