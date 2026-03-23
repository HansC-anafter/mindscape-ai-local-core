"""Runtime helpers for PlanBuilder."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Sequence

from .rule_based import attach_effective_playbooks

logger = logging.getLogger(__name__)


def select_model_for_plan(
    builder: Any,
    risk_level: str = "read",
    profile_id: Optional[str] = None,
) -> str:
    """Select the model used for plan generation."""
    if builder.model_name:
        return builder.model_name

    if builder.stage_router:
        try:
            from backend.app.services.conversation.capability_profile import (
                CapabilityProfileRegistry,
            )

            profile = builder.stage_router.get_profile_for_stage(
                "plan_generation",
                risk_level=risk_level,
            )
            registry = CapabilityProfileRegistry()
            cache_key = profile_id or "default-user"
            if cache_key not in builder._llm_manager_cache:
                from backend.app.shared.llm_provider_helper import (
                    create_llm_provider_manager,
                )

                config = builder.config_store.get_or_create_config(cache_key)
                builder._llm_manager_cache[cache_key] = create_llm_provider_manager(
                    openai_key=config.agent_backend.openai_api_key,
                    anthropic_key=config.agent_backend.anthropic_api_key,
                    vertex_api_key=config.agent_backend.vertex_api_key,
                    vertex_project_id=config.agent_backend.vertex_project_id,
                    vertex_location=config.agent_backend.vertex_location,
                )
            llm_manager = builder._llm_manager_cache[cache_key]
            model_name = registry.select_model(
                profile,
                llm_manager,
                profile_id=profile_id,
            )
            if model_name:
                return model_name
        except Exception as exc:
            logger.debug("Failed to use stage_router: %s, trying next option", exc)

    if builder.capability_profile:
        try:
            from backend.app.services.conversation.capability_profile import (
                CapabilityProfile,
                CapabilityProfileRegistry,
            )

            profile = CapabilityProfile(builder.capability_profile)
            registry = CapabilityProfileRegistry()
            cache_key = profile_id or "default-user"
            if cache_key not in builder._llm_manager_cache:
                from backend.app.shared.llm_provider_helper import (
                    create_llm_provider_manager,
                )

                config = builder.config_store.get_or_create_config(cache_key)
                builder._llm_manager_cache[cache_key] = create_llm_provider_manager(
                    openai_key=config.agent_backend.openai_api_key,
                    anthropic_key=config.agent_backend.anthropic_api_key,
                    vertex_api_key=config.agent_backend.vertex_api_key,
                    vertex_project_id=config.agent_backend.vertex_project_id,
                    vertex_location=config.agent_backend.vertex_location,
                )
            llm_manager = builder._llm_manager_cache[cache_key]
            model_name = registry.select_model(
                profile,
                llm_manager,
                profile_id=profile_id,
            )
            if model_name:
                return model_name
        except Exception as exc:
            logger.debug(
                "Failed to use capability_profile: %s, trying next option",
                exc,
            )

    try:
        from backend.app.services.conversation.capability_profile import (
            CapabilityProfile,
            CapabilityProfileRegistry,
        )
        from backend.app.services.system_settings_store import SystemSettingsStore

        settings_store = SystemSettingsStore()
        mapping = settings_store.get_capability_profile_mapping()
        profile_name = mapping.get("plan_generation", "precise")
        profile = CapabilityProfile(profile_name)
        registry = CapabilityProfileRegistry()
        cache_key = profile_id or "default-user"
        if cache_key not in builder._llm_manager_cache:
            from backend.app.shared.llm_provider_helper import (
                create_llm_provider_manager,
            )

            config = builder.config_store.get_or_create_config(cache_key)
            builder._llm_manager_cache[cache_key] = create_llm_provider_manager(
                openai_key=config.agent_backend.openai_api_key,
                anthropic_key=config.agent_backend.anthropic_api_key,
                vertex_api_key=config.agent_backend.vertex_api_key,
                vertex_project_id=config.agent_backend.vertex_project_id,
                vertex_location=config.agent_backend.vertex_location,
            )
        llm_manager = builder._llm_manager_cache[cache_key]
        model_name = registry.select_model(
            profile,
            llm_manager,
            profile_id=profile_id,
        )
        if model_name:
            return model_name
    except Exception as exc:
        logger.debug("Failed to use SystemSettings: %s, trying next option", exc)

    from backend.app.shared.llm_provider_helper import get_model_name_from_chat_model

    model_name = get_model_name_from_chat_model()
    if model_name:
        logger.debug("Using chat_model fallback: %s", model_name)
        return model_name

    logger.error(
        "PlanBuilder: All model selection methods failed. "
        "Configure chat_model in system settings."
    )
    raise ValueError("No chat model configured. Set chat_model in system settings.")


async def ensure_external_backend_loaded(
    builder: Any,
    profile_id: Optional[str] = None,
) -> None:
    """Load the external backend once if configured."""
    if builder._external_backend_loaded:
        return

    builder._external_backend_loaded = True

    try:
        if profile_id:
            config = builder.config_store.get_or_create_config(profile_id)
            external_config = getattr(config, "external_backend", None)

            if external_config and isinstance(external_config, dict):
                from backend.app.services.external_backend import load_external_backend

                builder.external_backend = await load_external_backend(external_config)
                if builder.external_backend:
                    logger.info(
                        "Loaded external backend from user config for profile %s",
                        profile_id,
                    )
                    return

        driver = os.getenv("EXTERNAL_BACKEND_DRIVER")
        if driver:
            options = {
                "base_url": os.getenv("EXTERNAL_BACKEND_URL"),
                "api_key": os.getenv("EXTERNAL_BACKEND_API_KEY"),
                "timeout": float(os.getenv("EXTERNAL_BACKEND_TIMEOUT", "1.5")),
            }
            from backend.app.services.external_backend import load_external_backend

            builder.external_backend = await load_external_backend(
                {"driver": driver, "options": options}
            )
            if builder.external_backend:
                logger.info("Loaded external backend from environment variables")
                return

        logger.debug(
            "No external backend configured, will skip cloud-enhanced retrieval"
        )
    except Exception as exc:
        logger.warning(
            "Failed to load external backend: %s, will skip cloud-enhanced retrieval",
            exc,
        )
        builder.external_backend = None


async def create_or_link_phase(
    builder: Any,
    execution_plan: Any,
    project_id: str,
    message_id: str,
    project_assignment_decision: Optional[Dict[str, Any]] = None,
) -> None:
    """Create or link a project phase for an execution plan."""
    try:
        from backend.app.services.project.project_phase_manager import (
            ProjectPhaseManager,
        )

        phase_manager = ProjectPhaseManager(store=builder.store)
        assignment_relation = (
            project_assignment_decision.get("relation")
            if project_assignment_decision
            else None
        )
        phase_kind = (
            "revision" if assignment_relation == "same_project" else "initial_brief"
        )

        phase = await phase_manager.create_phase(
            project_id=project_id,
            message_id=message_id,
            summary=execution_plan.plan_summary
            or execution_plan.user_request_summary
            or "",
            kind=phase_kind,
            workspace_id=execution_plan.workspace_id,
            execution_plan_id=execution_plan.id,
        )

        execution_plan.phase_id = phase.id
        execution_plan.project_id = project_id
        logger.info(
            "Created phase %s for project %s, kind=%s, message_id=%s",
            phase.id,
            project_id,
            phase_kind,
            message_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to create phase for execution plan: %s",
            exc,
            exc_info=True,
        )


async def finalize_execution_plan(
    builder: Any,
    *,
    execution_plan: Any,
    project_id: Optional[str],
    message_id: str,
    project_assignment_decision: Optional[Dict[str, Any]],
    playbooks_to_use: Optional[Sequence[Dict[str, Any]]],
) -> Any:
    """Apply post-build phase linking and effective-playbook metadata."""
    if project_id and execution_plan:
        await create_or_link_phase(
            builder,
            execution_plan=execution_plan,
            project_id=project_id,
            message_id=message_id,
            project_assignment_decision=project_assignment_decision,
        )

    attach_effective_playbooks(execution_plan, playbooks_to_use)
    return execution_plan
