"""
Local Intent Registry Adapter - Wraps existing IntentLLMExtractor

Temporarily calls existing LLM extractor directly, behavior unchanged.
Future: Can be extended to load intent definitions from built-in YAML.
"""

from typing import Any, Dict, List, Optional
from ...core.ports.intent_registry_port import (
    IntentRegistryPort,
    IntentResolutionResult,
    IntentDefinition
)
from ...core.execution_context import ExecutionContext
from ...services.intent_llm_extractor import IntentLLMExtractor


class LocalIntentRegistryAdapter(IntentRegistryPort):
    """
    Local Intent Registry Adapter - Wraps existing IntentLLMExtractor

    Temporarily calls existing LLM extractor directly, behavior unchanged.
    Future: Can be extended to load intent definitions from built-in YAML.
    """

    def __init__(self, default_locale: str = "en"):
        self.default_locale = default_locale
        self.llm_extractor = IntentLLMExtractor(default_locale=default_locale)

    async def resolve_intent(
        self,
        user_input: str,
        ctx: ExecutionContext,
        context: Optional[str] = None,
        locale: Optional[str] = None
    ) -> IntentResolutionResult:
        """
        Resolve Intent - Temporarily calls existing LLM extractor directly
        """
        result = await self.llm_extractor.extract(
            message=user_input,
            context=context or "",
            locale=locale or self.default_locale
        )

        return IntentResolutionResult(
            intents=result.get("intents", []),
            themes=result.get("themes", []),
            confidence=result.get("confidence"),
            llm_analysis=result.get("llm_analysis")
        )

    async def list_available_intents(
        self,
        ctx: ExecutionContext
    ) -> List[IntentDefinition]:
        """
        List available Intents - Temporarily returns empty list

        Future: Can load from built-in YAML:
        - workspace.generic.brain_dump
        - workspace.generic.summarize
        - reading.assist.highlight
        - planning.simple_todo
        """
        return []

