"""Lens helpers for runtime workflow execution."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def inject_lens_context(
    *,
    profile_id: str,
    workspace_id: Optional[str],
    execution_id: str,
    normalized_inputs: Dict[str, Any],
) -> Optional[Any]:
    from backend.app.core.feature_flags import FeatureFlags

    if not FeatureFlags.USE_EFFECTIVE_LENS_RESOLVER:
        return None

    try:
        from backend.app.services.lens.lens_execution_injector import (
            LensExecutionInjector,
        )

        injector = LensExecutionInjector()
        lens_context = injector.prepare_lens_context(
            profile_id=profile_id,
            workspace_id=workspace_id,
            session_id=execution_id,
        )
        if not lens_context:
            return None

        logger.info(
            "PlaybookRunExecutor: Lens context prepared, hash=%s",
            lens_context.get("effective_lens_hash"),
        )
        if "system_prompt_additions" in lens_context:
            normalized_inputs["_lens_system_prompt"] = lens_context[
                "system_prompt_additions"
            ]
        if "anti_goals" in lens_context:
            normalized_inputs["_lens_anti_goals"] = lens_context["anti_goals"]
        if "emphasized_values" in lens_context:
            normalized_inputs["_lens_emphasized_values"] = lens_context[
                "emphasized_values"
            ]
        return lens_context.get("effective_lens")
    except Exception as exc:
        logger.warning(
            "PlaybookRunExecutor: Failed to inject lens context: %s",
            exc,
            exc_info=True,
        )
        return None


def generate_lens_receipt(
    *,
    execution_id: str,
    workspace_id: Optional[str],
    runtime_result: Any,
    effective_lens: Any,
) -> None:
    if not effective_lens:
        return

    from backend.app.core.feature_flags import FeatureFlags

    if not FeatureFlags.USE_EFFECTIVE_LENS_RESOLVER:
        return

    try:
        from backend.app.services.lens.lens_execution_injector import (
            LensExecutionInjector,
        )

        injector = LensExecutionInjector()
        outputs = getattr(runtime_result, "outputs", None)
        output_text = str(outputs) if outputs else None
        receipt = injector.generate_receipt(
            execution_id=execution_id,
            workspace_id=workspace_id,
            effective_lens=effective_lens,
            output=output_text,
            base_output=None,
        )
        if receipt:
            logger.info(
                "PlaybookRunExecutor: Lens receipt generated for execution %s",
                execution_id,
            )
    except Exception as exc:
        logger.warning(
            "PlaybookRunExecutor: Failed to generate lens receipt: %s",
            exc,
            exc_info=True,
        )
