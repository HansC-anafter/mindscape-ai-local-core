import asyncio
import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi import Path as PathParam

from backend.app.models.model_provider import ModelType
from backend.app.models.workspace import (
    Workspace,
    WorkspaceChatModelOption,
    WorkspaceChatModelPreferenceRequest,
    WorkspaceChatModelPreferenceResponse,
)
from backend.app.routes.workspace_dependencies import get_workspace
from backend.app.services.external_agents.core.registry import get_runtime_registry
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.model_config_store import ModelConfigStore
from backend.features.workspace.chat.utils.llm_provider import (
    get_llm_provider,
    get_llm_provider_manager,
)

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()

_PREFERRED_CHAT_MODEL_KEY = "preferred_chat_model"


def _utc_now():
    return datetime.now(timezone.utc)


async def _list_enabled_chat_models():
    model_store = ModelConfigStore()
    models = await asyncio.to_thread(
        model_store.get_all_models,
        ModelType.CHAT,
        True,
        None,
    )
    if models:
        return models
    await asyncio.to_thread(model_store.initialize_default_models)
    return await asyncio.to_thread(
        model_store.get_all_models,
        ModelType.CHAT,
        True,
        None,
    )


async def _resolve_runtime_status(
    workspace_id: str,
    runtime_id: str,
) -> tuple[bool, Optional[str], Optional[str]]:
    registry = get_runtime_registry()
    registry.discover_agents()
    adapter = registry.get_adapter(runtime_id)
    if not adapter:
        return False, "unavailable", f"{runtime_id} is not registered"

    detail = {}
    if hasattr(adapter, "get_availability_detail"):
        detail = adapter.get_availability_detail(workspace_id=workspace_id) or {}
        available = bool(detail.get("available"))
        reason = detail.get("reason")
    else:
        available = bool(await adapter.is_available(workspace_id=workspace_id))
        reason = None

    if not available and not reason:
        reason = f"{runtime_id} is not connected for this workspace"

    auth_status = "unavailable"
    if available:
        if runtime_id == "codex_cli":
            auth_status = "host_session"
        elif runtime_id == "claude_code_cli":
            auth_status = "host_token"
        elif runtime_id == "gemini_cli":
            auth_status = "configured"
        else:
            auth_status = "unknown"

    return available, auth_status, reason


def _resolve_direct_llm_status(
    workspace: Workspace,
    model_name: str,
) -> tuple[bool, Optional[str], Optional[str]]:
    try:
        manager = get_llm_provider_manager(
            profile_id=workspace.owner_user_id,
            db_path=store.db_path,
        )
        provider, _ = get_llm_provider(
            model_name=model_name,
            llm_provider_manager=manager,
            profile_id=workspace.owner_user_id,
            db_path=store.db_path,
        )
        availability_check = getattr(provider, "is_model_available", None)
        if callable(availability_check):
            available, reason = availability_check(model_name)
            if not available:
                return False, "unavailable", reason or (
                    f"Model '{model_name}' is unavailable for the current provider."
                )
        return True, "configured", None
    except Exception as exc:
        return False, "unavailable", str(exc)


def _build_direct_llm_option(
    workspace: Workspace,
    model,
) -> WorkspaceChatModelOption:
    available, auth_status, disabled_reason = _resolve_direct_llm_status(
        workspace,
        model.model_name,
    )
    label = model.display_name or f"{model.model_name} · {model.provider_name}"
    return WorkspaceChatModelOption(
        id=f"direct_llm:{model.provider_name}:{model.model_name}",
        label=label,
        model_name=model.model_name,
        provider=model.provider_name,
        source_kind="direct_llm",
        runtime_id=None,
        available=available,
        auth_status=auth_status,
        disabled_reason=disabled_reason,
    )


def _build_executor_runtime_option(
    model,
    runtime_id: str,
    available: bool,
    auth_status: Optional[str],
    disabled_reason: Optional[str],
) -> WorkspaceChatModelOption:
    label = f"{model.display_name or model.model_name} via {runtime_id}"
    return WorkspaceChatModelOption(
        id=f"executor_runtime:{runtime_id}:{model.provider_name}:{model.model_name}",
        label=label,
        model_name=model.model_name,
        provider=model.provider_name,
        source_kind="executor_runtime",
        runtime_id=runtime_id,
        available=available,
        auth_status=auth_status,
        disabled_reason=disabled_reason,
    )


async def _build_available_options(workspace: Workspace) -> list[WorkspaceChatModelOption]:
    enabled_models = await _list_enabled_chat_models()
    runtime_id = workspace.resolved_executor_runtime

    if runtime_id:
        available, auth_status, disabled_reason = await _resolve_runtime_status(
            workspace.id,
            runtime_id,
        )
        return [
            _build_executor_runtime_option(
                model=model,
                runtime_id=runtime_id,
                available=available,
                auth_status=auth_status,
                disabled_reason=disabled_reason,
            )
            for model in enabled_models
        ]

    return [_build_direct_llm_option(workspace, model) for model in enabled_models]


def _find_matching_option(
    options: Iterable[WorkspaceChatModelOption],
    *,
    selection_id: Optional[str] = None,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    runtime_id: Optional[str] = None,
) -> Optional[WorkspaceChatModelOption]:
    options_list = list(options)
    if selection_id:
        for option in options_list:
            if option.id == selection_id:
                return option

    normalized_model_name = (model_name or "").strip()
    normalized_provider = (provider or "").strip()
    normalized_runtime_id = (runtime_id or "").strip()

    for option in options_list:
        if normalized_model_name and option.model_name != normalized_model_name:
            continue
        if normalized_provider and option.provider != normalized_provider:
            continue
        if normalized_runtime_id and option.runtime_id != normalized_runtime_id:
            continue
        return option
    return None


def _resolve_current_selection(
    workspace: Workspace,
    options: list[WorkspaceChatModelOption],
) -> Optional[WorkspaceChatModelOption]:
    metadata = workspace.metadata or {}
    stored = metadata.get(_PREFERRED_CHAT_MODEL_KEY)
    if isinstance(stored, dict):
        matched = _find_matching_option(
            options,
            selection_id=stored.get("id"),
            model_name=stored.get("model_name"),
            provider=stored.get("provider"),
            runtime_id=stored.get("runtime_id"),
        )
        if matched:
            return matched
    return None


async def _build_preference_response(
    workspace: Workspace,
) -> WorkspaceChatModelPreferenceResponse:
    options = await _build_available_options(workspace)
    current_selection = _resolve_current_selection(workspace, options)
    return WorkspaceChatModelPreferenceResponse(
        workspace_id=workspace.id,
        current_selection=current_selection,
        available_models=options,
        resolved_executor_runtime=workspace.resolved_executor_runtime,
    )


@router.get(
    "/{workspace_id}/chat-model-preference",
    response_model=WorkspaceChatModelPreferenceResponse,
)
async def get_workspace_chat_model_preference(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
) -> WorkspaceChatModelPreferenceResponse:
    return await _build_preference_response(workspace)


@router.put(
    "/{workspace_id}/chat-model-preference",
    response_model=WorkspaceChatModelPreferenceResponse,
)
async def put_workspace_chat_model_preference(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: WorkspaceChatModelPreferenceRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
) -> WorkspaceChatModelPreferenceResponse:
    options = await _build_available_options(workspace)
    selected = _find_matching_option(options, selection_id=request.selection_id)
    if not selected:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown chat model selection: {request.selection_id}",
        )
    if not selected.available:
        raise HTTPException(
            status_code=400,
            detail=selected.disabled_reason
            or f"Selected chat model is unavailable: {selected.id}",
        )

    metadata = dict(workspace.metadata or {})
    metadata[_PREFERRED_CHAT_MODEL_KEY] = selected.model_dump()
    workspace.metadata = metadata
    workspace.updated_at = _utc_now()
    updated = await store.update_workspace(workspace)
    logger.info(
        "Updated workspace chat model preference for %s: %s",
        workspace_id,
        selected.id,
    )
    return await _build_preference_response(updated)
