"""Compatibility shim for legacy `app.services.llm.core_llm` imports.

Capability packs such as `performance_direction` still call `core_llm_call()`
through this path. Hidden managed-provider fallback has been removed; callers
must route through a workspace-bound runtime or provide a new explicit managed
LLM path elsewhere.
"""

from __future__ import annotations

from typing import Any, Optional

from ...shared.llm_utils import extract_json_from_text


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
    return getattr(workspace, "resolved_executor_runtime", None) or getattr(
        workspace, "executor_runtime", None
    )


async def _call_via_runtime(
    *,
    workspace: Any,
    executor_runtime: str,
    system_prompt: Optional[str],
    user_message: str,
    response_format: str,
    model: Optional[str],
) -> Any:
    from ...services.workspace_agent_executor import WorkspaceAgentExecutor

    executor = WorkspaceAgentExecutor(workspace)
    if not await executor.check_agent_available(executor_runtime):
        raise RuntimeError(
            f"Executor runtime '{executor_runtime}' is not available for workspace "
            f"{getattr(workspace, 'id', '')}"
        )

    result = await executor.execute(
        task=_build_runtime_task(
            system_prompt=system_prompt,
            user_message=user_message,
            response_format=response_format,
        ),
        agent_id=executor_runtime,
        skip_preflight=True,
        context_overrides={
            "conversation_context": system_prompt or "",
            "model": model,
        },
    )
    if not result.success:
        raise RuntimeError(result.error or f"{executor_runtime} execution failed")

    output = (result.output or "").strip()
    if response_format == "json":
        parsed = extract_json_from_text(output)
        if parsed is None:
            raise ValueError(
                f"{executor_runtime} did not return valid JSON for core_llm_call"
            )
        return parsed
    return output


async def core_llm_call(
    *,
    user_message: str,
    system_prompt: Optional[str] = None,
    response_format: str = "text",
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    executor_runtime: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Compatibility entry point for capability-pack LLM calls."""
    workspace = await _load_workspace(workspace_id)
    resolved_runtime = executor_runtime or _resolve_workspace_runtime(workspace)

    if resolved_runtime and workspace is not None:
        return await _call_via_runtime(
            workspace=workspace,
            executor_runtime=resolved_runtime,
            system_prompt=system_prompt,
            user_message=user_message,
            response_format=response_format,
            model=model,
        )

    raise RuntimeError(
        "core_llm_call requires an explicit workspace executor runtime; "
        "hidden managed LLM fallback has been removed"
    )
