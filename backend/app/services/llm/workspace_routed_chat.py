"""Workspace-aware chat completion entrypoint for routed tool-planning loops."""

from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

from backend.app.services.executor_route_context import load_executor_route_context
from backend.app.services.llm.governed_stage_router import (
    append_stage_route_decision,
    resolve_governed_stage_route,
)
from backend.app.shared.inference_config import InferenceConfig

logger = logging.getLogger(__name__)


def _prepare_provider_chat_kwargs(
    *,
    provider: Any,
    model_name: Optional[str],
    max_tokens: Optional[int],
    extra_kwargs: dict[str, Any],
) -> dict[str, Any]:
    signature = inspect.signature(provider.chat_completion)
    parameters = signature.parameters
    accepts_var_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in parameters.values()
    )

    call_kwargs: dict[str, Any] = {}
    if model_name and ("model" in parameters or accepts_var_kwargs):
        call_kwargs["model"] = model_name

    for key, value in extra_kwargs.items():
        if value is None:
            continue
        if key in parameters or accepts_var_kwargs:
            call_kwargs[key] = value

    if max_tokens is not None:
        resolved_max = InferenceConfig.get_max_tokens(
            model_name,
            caller_default=max_tokens,
        )
        model_lower = str(model_name or "").lower()
        prefers_completion_tokens = (
            "gpt-5" in model_lower
            or "o1" in model_lower
            or "o3" in model_lower
            or "gemini" in model_lower
        )
        if prefers_completion_tokens and (
            "max_completion_tokens" in parameters or accepts_var_kwargs
        ):
            call_kwargs["max_completion_tokens"] = resolved_max
        elif "max_tokens" in parameters or accepts_var_kwargs:
            call_kwargs["max_tokens"] = resolved_max

    return call_kwargs


async def _load_workspace(workspace_id: Optional[str]) -> Optional[Any]:
    if not workspace_id:
        return None
    from backend.app.services.stores.postgres.workspaces_store import (
        PostgresWorkspacesStore,
    )

    return await PostgresWorkspacesStore().get_workspace(workspace_id)


def _build_runtime_chat_task(messages: list[dict[str, str]]) -> str:
    rendered_messages: list[str] = []
    for message in messages:
        role = str(message.get("role") or "message").strip() or "message"
        content = str(message.get("content") or "")
        rendered_messages.append(f"[{role}]\n{content}")
    return (
        "Continue the workspace conversation and return only the assistant response.\n\n"
        + "\n\n".join(rendered_messages)
    )


async def _call_via_workspace_runtime(
    *,
    workspace_id: Optional[str],
    executor_runtime: str,
    messages: list[dict[str, str]],
    model_name: Optional[str],
) -> str:
    workspace = await _load_workspace(workspace_id)
    if workspace is None:
        raise RuntimeError(
            "Workspace runtime route selected but workspace context is unavailable"
        )
    normalized_runtime = str(executor_runtime or "").strip().lower()
    if normalized_runtime == "codex_cli":
        from backend.app.services.llm.core_llm import core_llm_call

        return str(
            await core_llm_call(
                user_message=_build_runtime_chat_task(messages),
                response_format="text",
                workspace_id=workspace_id,
                executor_runtime="codex_cli",
                model=model_name,
                purpose="workspace_routed_chat",
            )
        ).strip()

    from backend.app.services.workspace_agent_executor import WorkspaceAgentExecutor

    executor = WorkspaceAgentExecutor(workspace)
    if not await executor.check_agent_available(normalized_runtime):
        raise RuntimeError(
            f"Executor runtime '{normalized_runtime}' is not available for workspace "
            f"{workspace_id or ''}"
        )

    result = await executor.execute(
        task=_build_runtime_chat_task(messages),
        agent_id=normalized_runtime,
        skip_preflight=True,
        context_overrides={"model": model_name},
    )
    if not result.success:
        raise RuntimeError(result.error or f"{normalized_runtime} execution failed")
    return str(result.output or "").strip()


async def chat_completion_with_workspace_route(
    *,
    messages: list[dict[str, str]],
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    provider: Any = None,
    llm_provider_manager: Any = None,
    route_context: Optional[dict[str, Any]] = None,
    purpose: str = "chat_completion",
    stage_name: Optional[str] = None,
    decision_log: Optional[list[dict[str, Any]]] = None,
    risk_level: str = "read",
    **kwargs: Any,
) -> str:
    """
    Centralized chat-completion entrypoint for playbook/execution-chat loops.

    If model-route-registry resolves a workspace executor runtime, that runtime
    owns generation. Managed provider chat completion is only used when no
    workspace executor runtime is configured.
    """

    resolved_route_context = route_context
    if resolved_route_context is None and workspace_id:
        try:
            resolved_route_context = await load_executor_route_context(workspace_id)
        except Exception:
            logger.warning(
                "Failed to load executor route context for workspace %s",
                workspace_id,
                exc_info=True,
            )
            resolved_route_context = None

    decision = await resolve_governed_stage_route(
        workspace_id=workspace_id,
        route_context=resolved_route_context,
        stage_name=stage_name,
        purpose=purpose,
        response_format="text",
        risk_level=risk_level,
        requested_model=model,
        llm_provider_manager=llm_provider_manager,
        profile_id=profile_id,
    )
    append_stage_route_decision(decision_log, decision)
    if provider is not None:
        logger.debug(
            "Ignoring caller-supplied provider object; provider construction is owned by model-routing-registry"
        )
        provider = None

    executor_runtime = str(decision.executor_runtime or "").strip().lower()
    if decision.route_mode == "workspace_runtime":
        return await _call_via_workspace_runtime(
            workspace_id=workspace_id,
            executor_runtime=executor_runtime,
            messages=messages,
            model_name=decision.model_name,
        )

    if decision.executor_runtime:
        raise RuntimeError(
            "Managed provider route is not allowed when workspace executor runtime is configured"
        )

    if provider is None:
        if not decision.model_name or not decision.provider_name:
            raise ValueError(
                "Managed provider route requires model and provider from "
                "model-routing-registry"
            )
        from backend.app.shared.llm_provider_helper import build_managed_llm_provider

        provider, _selection = build_managed_llm_provider(
            model_name=decision.model_name,
            provider_name=decision.provider_name,
            purpose=purpose,
        )

    logger.info(
        "workspace_routed_chat managed provider route %s "
        "(workspace=%s stage=%s reason=%s)",
        purpose,
        workspace_id,
        decision.stage_name,
        decision.decision_reason,
    )

    call_kwargs = _prepare_provider_chat_kwargs(
        provider=provider,
        model_name=decision.model_name,
        max_tokens=max_tokens,
        extra_kwargs=dict(kwargs),
    )
    return await provider.chat_completion(messages, **call_kwargs)
