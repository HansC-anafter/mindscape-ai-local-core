"""Compatibility shim for legacy `app.services.llm.core_llm` imports.

Capability packs such as `performance_direction` still call `core_llm_call()`
through this path. This shim makes that path real again and delegates to:

1. workspace-bound external runtimes (`codex_cli` via Codex pool, other CLI
   runtimes via the workspace executor bridge)
2. managed `core_llm.generate` when no executor runtime is configured
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import uuid
from typing import Any, Optional

from ...shared.llm_utils import extract_json_from_text
from backend.app.services.codex_runtime_failure_classifier import (
    classify_codex_cli_runtime_failure,
    should_retry_codex_runtime_fault,
)
from backend.app.services.external_agents.bridge.codex_cli_runner import (
    should_use_direct_codex_cli_subprocess,
)
from .governed_stage_router import (
    append_stage_route_decision,
    resolve_governed_stage_route,
)
from .core_llm_codex_cli import (
    build_codex_cli_command,
    codex_pool_wait_attempt_count,
    codex_error_text_from_result,
    merge_codex_env,
    parse_codex_success_output,
    resolve_codex_stall_timeout,
)

logger = logging.getLogger(__name__)


def _build_runtime_task(
    *,
    system_prompt: Optional[str],
    user_message: str,
    response_format: str,
) -> str:
    prompt_parts = []
    if system_prompt:
        prompt_parts.append(f"[System Prompt]\n{system_prompt}")
    prompt_parts.append(f"[User Request]\n{user_message}")
    if response_format == "json":
        prompt_parts.append("Return ONLY valid JSON. Do not wrap it in markdown fences.")
    return "\n\n".join(prompt_parts)


async def _load_workspace(workspace_id: Optional[str]) -> Optional[Any]:
    if not workspace_id:
        return None
    from ...services.stores.postgres.workspaces_store import PostgresWorkspacesStore

    return await PostgresWorkspacesStore().get_workspace(workspace_id)


def _resolve_workspace_runtime(workspace: Optional[Any]) -> Optional[str]:
    if workspace is None:
        return None
    return getattr(workspace, "resolved_executor_runtime", None)


def _runtime_failure_retryable(error: Any) -> bool:
    text = str(error or "").strip().lower()
    if not text:
        return True
    markers = (
        "no websocket client connected",
        "not available",
        "unavailable",
        "timed out",
        "timeout",
        "connection reset",
        "connection closed",
        "no active runner",
        "no concrete codex pool runtime",
        "no available codex runtimes in pool",
        "codex pool admission blocked",
        "no_runnable_runtimes",
        "preferred codex runtime unavailable",
    )
    return any(marker in text for marker in markers)


def _codex_runtime_failure_retryable(error: Any) -> bool:
    text = str(error or "").strip().lower()
    if _runtime_failure_retryable(text):
        return True
    return should_retry_codex_runtime_fault(text)


def _runtime_retry_delay(attempt_index: int) -> float:
    delays = (2.0, 4.0, 8.0, 16.0, 30.0)
    return delays[min(attempt_index, len(delays) - 1)]


async def _resolve_codex_pool_bundle(
    *,
    workspace: Any,
    excluded_runtime_ids: set[str],
) -> dict[str, Any]:
    from backend.app.services.codex_pool_runtime_router import (
        resolve_codex_pool_runtime_bundle,
    )

    workspace_id = str(getattr(workspace, "id", "") or "").strip()
    return await resolve_codex_pool_runtime_bundle(
        workspace_id=workspace_id,
        lease_owner_type="core_llm_call",
        lease_owner_id=workspace_id,
        excluded_runtime_ids=excluded_runtime_ids,
        fail_closed_session_lease=False,
        record_runtime_lease=False,
    )


async def _report_codex_runtime_fault(
    *,
    runtime_id: str,
    fault_kind: str,
    workspace_id: str,
    error_code: str = "runtime_error",
    error_text: str = "",
) -> None:
    if not runtime_id:
        return
    try:
        from backend.app.services.codex_pool_runtime_router import (
            report_codex_pool_runtime_fault,
        )

        await report_codex_pool_runtime_fault(
            runtime_id=runtime_id,
            fault_kind=fault_kind,
            workspace_id=workspace_id,
            error_code=error_code,
            error_text=error_text,
        )
    except Exception:
        logger.warning(
            "Failed to report Codex runtime fault for %s",
            runtime_id,
            exc_info=True,
        )


async def _call_via_direct_codex_runtime(
    *,
    workspace: Any,
    system_prompt: Optional[str],
    user_message: str,
    response_format: str,
    model: Optional[str],
) -> Any:
    from backend.app.services.external_agents.bridge.codex_cli_runner import (
        DEFAULT_CLI_STALL_TIMEOUT_SECONDS,
        resolve_codex_cli_binary,
        resolve_codex_cli_cwd,
        run_codex_cli_subprocess,
    )

    workspace_id = str(getattr(workspace, "id", "") or "").strip()
    binary = resolve_codex_cli_binary(os.environ.get("CODEX_CLI_PATH", "").strip())
    cwd = resolve_codex_cli_cwd(os.environ.get("HOST_PROJECT_PATH", "").strip())
    excluded_runtime_ids: set[str] = set()
    max_attempts = 1
    attempt = 1
    pool_wait_attempts = codex_pool_wait_attempt_count()
    pool_wait_index = 0
    last_runtime_error = ""

    while attempt <= max_attempts:
        bundle = await _resolve_codex_pool_bundle(
            workspace=workspace,
            excluded_runtime_ids=excluded_runtime_ids,
        )
        pool_error = str(bundle.get("error") or bundle.get("warning") or "").strip()
        if pool_error:
            if (
                _runtime_failure_retryable(pool_error)
                and pool_wait_index < pool_wait_attempts - 1
            ):
                logger.warning(
                    "Codex pool temporarily unavailable for core_llm_call "
                    "(wait %d/%d): %s",
                    pool_wait_index + 1,
                    pool_wait_attempts,
                    pool_error,
                )
                await asyncio.sleep(_runtime_retry_delay(pool_wait_index))
                pool_wait_index += 1
                continue
            if attempt > 1 and last_runtime_error:
                raise RuntimeError(
                    f"Preferred agent 'codex_cli' failed: {last_runtime_error} "
                    f"(pool failover unavailable: {pool_error})"
                )
            raise RuntimeError(f"Preferred agent 'codex_cli' failed: {pool_error}")

        selected_runtime_id = str(bundle.get("selected_runtime_id") or "").strip()
        if not selected_runtime_id:
            raise RuntimeError(
                "Preferred agent 'codex_cli' failed: no concrete Codex pool runtime is bound"
            )

        try:
            max_attempts = max(
                max_attempts,
                int(
                    bundle.get("available_quota_scope_count")
                    or bundle.get("available_runtime_count")
                    or 1
                ),
            )
        except (TypeError, ValueError):
            pass

        with tempfile.NamedTemporaryFile(
            prefix="core_llm_codex_last_",
            suffix=".txt",
            delete=False,
        ) as tmp:
            last_message_path = tmp.name

        task = _build_runtime_task(
            system_prompt=system_prompt,
            user_message=user_message,
            response_format=response_format,
        )
        cmd = build_codex_cli_command(
            binary=binary,
            last_message_path=last_message_path,
            task=task,
            model=model,
        )

        stall_timeout_raw = os.environ.get(
            "MINDSCAPE_CLI_STALL_TIMEOUT_SECONDS",
            str(DEFAULT_CLI_STALL_TIMEOUT_SECONDS),
        ).strip()
        stall_timeout = resolve_codex_stall_timeout(
            raw_value=stall_timeout_raw,
            default_timeout=DEFAULT_CLI_STALL_TIMEOUT_SECONDS,
        )

        try:
            result = await run_codex_cli_subprocess(
                cmd=cmd,
                cwd=cwd,
                env=merge_codex_env(bundle.get("env")),
                last_message_path=last_message_path,
                execution_id=f"core-llm-{uuid.uuid4()}",
                timeout=300.0,
                stall_timeout=min(300.0, stall_timeout),
            )
        except asyncio.TimeoutError as exc:
            result = None
            error_text = str(exc).strip() or "codex_cli subprocess timed out"
        finally:
            try:
                os.unlink(last_message_path)
            except OSError:
                pass

        if result is not None and result.returncode == 0 and result.output_text:
            return parse_codex_success_output(
                output_text=result.output_text,
                response_format=response_format,
            )

        if result is not None:
            error_text = codex_error_text_from_result(result)
        runtime_fault = classify_codex_cli_runtime_failure(error_text)
        fault_kind = str(runtime_fault.get("fault_kind") or "runtime").strip()
        error_code = str(runtime_fault.get("error_code") or "runtime_error").strip()
        quota_fault = fault_kind == "quota"
        auth_fault = fault_kind == "auth"
        retryable_fault = should_retry_codex_runtime_fault(error_text)
        if quota_fault:
            await _report_codex_runtime_fault(
                runtime_id=selected_runtime_id,
                fault_kind="quota",
                workspace_id=workspace_id,
                error_text=error_text,
            )
        elif auth_fault or retryable_fault:
            await _report_codex_runtime_fault(
                runtime_id=selected_runtime_id,
                fault_kind="auth",
                workspace_id=workspace_id,
                error_code="timeout" if retryable_fault and not auth_fault else error_code,
            )

        if not (quota_fault or auth_fault or retryable_fault):
            raise RuntimeError(
                f"Preferred agent 'codex_cli' failed on bound runtime "
                f"'{selected_runtime_id}': {error_text}"
            )
        last_runtime_error = error_text
        excluded_runtime_ids.add(selected_runtime_id)
        if attempt >= max_attempts:
            raise RuntimeError(
                f"Preferred agent 'codex_cli' failed on bound runtime "
                f"'{selected_runtime_id}': {error_text}"
            )
        attempt += 1

    raise RuntimeError("Preferred agent 'codex_cli' failed before returning output")


async def _call_via_runtime(
    *,
    workspace: Any,
    executor_runtime: str,
    system_prompt: Optional[str],
    user_message: str,
    response_format: str,
    model: Optional[str],
) -> Any:
    normalized_runtime = str(executor_runtime or "").strip().lower()
    if normalized_runtime == "codex_cli" and should_use_direct_codex_cli_subprocess():
        return await _call_via_direct_codex_runtime(
            workspace=workspace,
            system_prompt=system_prompt,
            user_message=user_message,
            response_format=response_format,
            model=model,
        )

    from ...services.workspace_agent_executor import WorkspaceAgentExecutor

    executor = WorkspaceAgentExecutor(workspace)
    attempts_raw = os.environ.get("MINDSCAPE_CORE_LLM_RUNTIME_ATTEMPTS", "6").strip()
    try:
        max_attempts = max(1, min(8, int(attempts_raw)))
    except ValueError:
        max_attempts = 6

    result = None
    last_error = ""
    task = _build_runtime_task(
        system_prompt=system_prompt,
        user_message=user_message,
        response_format=response_format,
    )
    for attempt in range(max_attempts):
        result = await executor.execute(
            task=task,
            agent_id=normalized_runtime,
            skip_preflight=True,
            context_overrides={
                "conversation_context": system_prompt or "",
                "model": model,
            },
        )
        if result.success:
            break
        last_error = str(
            result.error or result.output or f"{normalized_runtime} execution failed"
        ).strip()
        retryable = (
            _codex_runtime_failure_retryable(last_error)
            if normalized_runtime == "codex_cli"
            else _runtime_failure_retryable(last_error)
        )
        if not retryable or attempt >= max_attempts - 1:
            break
        await asyncio.sleep(_runtime_retry_delay(attempt))

    if result is None or not result.success:
        raise RuntimeError(last_error or f"{normalized_runtime} execution failed")

    output = (result.output or "").strip()
    if response_format == "json":
        parsed = extract_json_from_text(output)
        if parsed is None:
            raise ValueError(
                f"{normalized_runtime} did not return valid JSON for core_llm_call"
            )
        return parsed
    return output


async def _call_via_managed_llm(
    *,
    workspace_id: Optional[str],
    profile_id: Optional[str],
    system_prompt: Optional[str],
    user_message: str,
    response_format: str,
    model: Optional[str],
    kwargs: dict[str, Any],
) -> Any:
    from ...capabilities.core_llm.services.generate import run as generate_text

    result = await generate_text(
        prompt=user_message,
        system_prompt=system_prompt,
        workspace_id=workspace_id,
        profile_id=profile_id,
        model=model,
        **kwargs,
    )
    text = str(result.get("text", "") or "").strip()
    if response_format == "json":
        parsed = extract_json_from_text(text)
        if parsed is None:
            raise ValueError("Managed core_llm did not return valid JSON")
        return parsed
    return text


async def core_llm_call(
    *,
    user_message: str,
    system_prompt: Optional[str] = None,
    response_format: str = "text",
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    executor_runtime: Optional[str] = None,
    model: Optional[str] = None,
    route_context: Optional[dict[str, Any]] = None,
    stage_name: Optional[str] = None,
    purpose: str = "core_llm_call",
    decision_log: Optional[list[dict[str, Any]]] = None,
    risk_level: str = "read",
    **kwargs: Any,
) -> Any:
    """Compatibility entry point for capability-pack LLM calls."""
    workspace = await _load_workspace(workspace_id)
    resolved_route_context = route_context
    if resolved_route_context is None and workspace is not None:
        from backend.app.services.executor_route_context import build_executor_route_context

        resolved_route_context = build_executor_route_context(workspace)

    decision = await resolve_governed_stage_route(
        workspace_id=workspace_id,
        route_context=resolved_route_context,
        stage_name=stage_name,
        purpose=purpose,
        response_format=response_format,
        risk_level=risk_level,
        requested_model=model,
        explicit_executor_runtime=executor_runtime or _resolve_workspace_runtime(workspace),
    )
    append_stage_route_decision(decision_log, decision)

    if decision.route_mode == "workspace_runtime":
        if workspace is None:
            raise RuntimeError(
                "Workspace runtime route selected but workspace context is unavailable"
            )
        return await _call_via_runtime(
            workspace=workspace,
            executor_runtime=decision.executor_runtime or executor_runtime,
            system_prompt=system_prompt,
            user_message=user_message,
            response_format=response_format,
            model=decision.model_name,
        )

    if decision.executor_runtime:
        raise RuntimeError(
            "Managed provider route is not allowed when workspace executor runtime is configured"
        )

    logger.info(
        "core_llm_call using managed provider path "
        "(workspace_id=%s, stage=%s, runtime=%s, reason=%s)",
        workspace_id,
        decision.stage_name,
        decision.executor_runtime,
        decision.decision_reason,
    )
    return await _call_via_managed_llm(
        workspace_id=workspace_id,
        profile_id=profile_id,
        system_prompt=system_prompt,
        user_message=user_message,
        response_format=response_format,
        model=decision.model_name,
        kwargs=kwargs,
    )
