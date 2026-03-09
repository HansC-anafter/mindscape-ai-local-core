import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def build_llm_provider(
    *,
    workspace: Optional[Any] = None,
    executor_runtime: Optional[str] = None,
    allow_with_executor_runtime: bool = False,
) -> Any:
    from backend.app.shared.llm_provider_helper import (
        build_managed_llm_provider,
    )

    provider, selection = build_managed_llm_provider(
        workspace=workspace,
        executor_runtime=executor_runtime,
        default_model="gpt-4o-mini",
        allow_with_executor_runtime=allow_with_executor_runtime,
        purpose="conversation_llm_factory",
    )
    logger.info(
        "LLM provider factory resolved provider=%s model=%s purpose=conversation_llm_factory",
        selection.provider_name,
        selection.model_name,
    )
    return provider
