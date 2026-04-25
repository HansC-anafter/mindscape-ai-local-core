"""
Workspace-aware chat completion entrypoint for managed tool-planning loops.
"""

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


_AGENTIC_EXECUTOR_RUNTIMES = frozenset({"codex_cli", "gemini_cli", "claude_code_cli"})


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

    These loops still use managed provider chat-completion semantics because the
    current executor runtimes are agentic CLI surfaces, not plain text-only chat
    adapters. We still load and propagate workspace route context here so the
    remaining managed path is centralized and observable.
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

    if provider is None:
        if llm_provider_manager is None:
            from backend.app.services.config_store import ConfigStore
            from backend.app.services.playbook.llm_provider_manager import (
                PlaybookLLMProviderManager,
            )

            llm_provider_manager = PlaybookLLMProviderManager(ConfigStore())

        llm_manager = llm_provider_manager.get_llm_manager(profile_id or "default-user")
        provider = llm_provider_manager.get_llm_provider(llm_manager)

    executor_runtime = str(decision.executor_runtime or "").strip().lower()
    if executor_runtime in _AGENTIC_EXECUTOR_RUNTIMES:
        logger.info(
            "workspace_routed_chat stage route %s "
            "(workspace=%s stage=%s runtime=%s concrete_runtime=%s reason=%s)",
            purpose,
            workspace_id,
            decision.stage_name,
            executor_runtime,
            decision.concrete_runtime_id,
            decision.decision_reason,
        )
    elif executor_runtime:
        logger.info(
            "workspace_routed_chat stage route %s "
            "(workspace=%s stage=%s runtime=%s reason=%s)",
            purpose,
            workspace_id,
            decision.stage_name,
            executor_runtime,
            decision.decision_reason,
        )
    else:
        logger.info(
            "workspace_routed_chat stage route %s "
            "(workspace=%s stage=%s runtime=managed reason=%s)",
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
