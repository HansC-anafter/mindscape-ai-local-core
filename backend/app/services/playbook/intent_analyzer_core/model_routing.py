from typing import Any, Optional, Tuple

from backend.app.services.llm.governed_stage_router import (
    resolve_stage_capability_profile,
    resolve_stage_model_name,
)


def ensure_llm_provider_manager(llm_provider_manager: Optional[Any]) -> Any:
    """Lazily create the playbook LLM provider manager used by intent analysis."""
    if llm_provider_manager:
        return llm_provider_manager

    from backend.app.services.config_store import ConfigStore
    from backend.app.services.playbook.llm_provider_manager import (
        PlaybookLLMProviderManager,
    )

    return PlaybookLLMProviderManager(ConfigStore())


def resolve_intent_stage_model(
    *,
    llm_provider_manager: Optional[Any],
    profile_id: Optional[str],
    stage_name: str,
    risk_level: str,
) -> Tuple[Any, Optional[str]]:
    """Resolve the governed stage model through the existing registry path."""
    manager = ensure_llm_provider_manager(llm_provider_manager)
    resolved_profile_id = profile_id or "default-user"
    model_name = resolve_stage_model_name(
        requested_model=None,
        capability_profile=resolve_stage_capability_profile(
            stage_name,
            risk_level,
        ),
        llm_provider_manager=manager,
        profile_id=resolved_profile_id,
    )
    return manager, model_name
