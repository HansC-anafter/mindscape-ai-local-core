"""
Canonical stage-routing decision helper for governed LLM execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from backend.app.models.model_provider import ModelType as ProviderModelType
from backend.app.services.conversation.stage_profile_mapper import StageProfileMapper
from backend.app.services.executor_route_context import load_executor_route_context

@dataclass(frozen=True)
class StageRouteDecision:
    workspace_id: Optional[str]
    stage_name: str
    purpose: str
    route_mode: str
    executor_runtime: Optional[str]
    concrete_runtime_id: Optional[str]
    capability_profile: Optional[str]
    model_name: Optional[str]
    provider_name: Optional[str]
    decision_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_stage_name(
    *,
    stage_name: Optional[str],
    purpose: str,
) -> str:
    normalized = str(stage_name or "").strip().lower()
    if normalized:
        return normalized

    purpose_lower = str(purpose or "").strip().lower()
    if "intent" in purpose_lower:
        return "intent_analysis"
    if "execution_selection" in purpose_lower or "workspace_tool_execution_select" in purpose_lower:
        return "execution_selection"
    if "core_llm" in purpose_lower:
        return "generic_generation"
    if "format_retry" in purpose_lower:
        return "tool_call_repair"
    if "tool_loop" in purpose_lower or "execution_chat_agent" in purpose_lower:
        return "tool_call_generation"
    if "playbook_runner" in purpose_lower:
        return "plan_generation"
    return "response_formatting"


def resolve_stage_capability_profile(stage_name: str, risk_level: str) -> Optional[str]:
    if stage_name not in StageProfileMapper.STAGE_PROFILE_MAP:
        return None

    try:
        profile = StageProfileMapper().get_profile_for_stage(stage_name, risk_level=risk_level)
    except Exception:
        return None

    return getattr(profile, "value", None) or str(profile)


def resolve_stage_model_route(
    *,
    requested_model: Optional[str],
    capability_profile: Optional[str],
    llm_provider_manager: Any = None,
    profile_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    from backend.app.services.model_routing_policy_service import (
        ModelRoutingPolicyService,
    )

    routing_service = ModelRoutingPolicyService()
    chat_route = routing_service.resolve_chat_default()

    if requested_model:
        try:
            route = routing_service.resolve_registered_model(
                model_name=requested_model,
                model_type=ProviderModelType.CHAT,
                source="requested_model",
            )
            return route.model_name, route.provider
        except ValueError:
            if requested_model == chat_route.model_name:
                return chat_route.model_name, chat_route.provider
            return requested_model, None

    if not capability_profile:
        return chat_route.model_name, chat_route.provider

    try:
        profile_route = routing_service.resolve_profile_model(
            profile=str(capability_profile),
            scope="local",
            model_type=ProviderModelType.CHAT,
        )
        if profile_route.model_name:
            return profile_route.model_name, profile_route.provider
    except ValueError:
        raise
    except Exception:
        pass

    return chat_route.model_name, chat_route.provider


def resolve_stage_model_name(
    *,
    requested_model: Optional[str],
    capability_profile: Optional[str],
    llm_provider_manager: Any = None,
    profile_id: Optional[str] = None,
) -> Optional[str]:
    model_name, _provider_name = resolve_stage_model_route(
        requested_model=requested_model,
        capability_profile=capability_profile,
        llm_provider_manager=llm_provider_manager,
        profile_id=profile_id,
    )
    return model_name


async def resolve_governed_stage_route(
    *,
    workspace_id: Optional[str],
    route_context: Optional[dict[str, Any]] = None,
    stage_name: Optional[str] = None,
    purpose: str = "chat_completion",
    response_format: str = "text",
    risk_level: str = "read",
    requested_model: Optional[str] = None,
    explicit_executor_runtime: Optional[str] = None,
    llm_provider_manager: Any = None,
    profile_id: Optional[str] = None,
) -> StageRouteDecision:
    resolved_stage = _normalize_stage_name(stage_name=stage_name, purpose=purpose)
    resolved_route_context = route_context
    if resolved_route_context is None and workspace_id:
        try:
            resolved_route_context = await load_executor_route_context(workspace_id)
        except Exception:
            resolved_route_context = None

    executor_runtime = str(
        explicit_executor_runtime
        or (resolved_route_context or {}).get("executor_runtime")
        or ""
    ).strip().lower() or None
    concrete_runtime_id = str(
        (resolved_route_context or {}).get("concrete_runtime_id") or ""
    ).strip() or None
    capability_profile = resolve_stage_capability_profile(resolved_stage, risk_level)
    resolved_model_name, resolved_provider_name = resolve_stage_model_route(
        requested_model=requested_model,
        capability_profile=capability_profile,
        llm_provider_manager=llm_provider_manager,
        profile_id=profile_id,
    )

    if executor_runtime:
        return StageRouteDecision(
            workspace_id=workspace_id,
            stage_name=resolved_stage,
            purpose=purpose,
            route_mode="workspace_runtime",
            executor_runtime=executor_runtime,
            concrete_runtime_id=concrete_runtime_id,
            capability_profile=capability_profile,
            model_name=resolved_model_name,
            provider_name=resolved_provider_name,
            decision_reason="workspace_runtime_stage",
        )

    return StageRouteDecision(
        workspace_id=workspace_id,
        stage_name=resolved_stage,
        purpose=purpose,
        route_mode="managed_provider",
        executor_runtime=None,
        concrete_runtime_id=None,
        capability_profile=capability_profile,
        model_name=resolved_model_name,
        provider_name=resolved_provider_name,
        decision_reason="no_workspace_runtime",
    )


def append_stage_route_decision(
    decision_log: Optional[list[dict[str, Any]]],
    decision: StageRouteDecision,
) -> None:
    if decision_log is None:
        return
    decision_log.append(decision.to_dict())
