"""
Local LLM Backend
Executes agents using local LLM providers (OpenAI, Anthropic)
"""

import os
import logging
from typing import Dict, List, Optional, Any

from backend.app.services.agent_backend import AgentBackend
from backend.app.models.mindscape import (
    MindscapeProfile, IntentCard, AgentResponse
)
from backend.app.services.agent_runner import (
    LLMProviderManager, AgentPromptBuilder
)

logger = logging.getLogger(__name__)


class LocalLLMBackend(AgentBackend):
    """Local LLM-based agent backend"""

    def __init__(self, openai_key: Optional[str] = None, anthropic_key: Optional[str] = None):
        self.llm_manager = LLMProviderManager(openai_key=openai_key, anthropic_key=anthropic_key)
        self.prompt_builder = AgentPromptBuilder()

    async def run_agent(
        self,
        task: str,
        agent_type: str,
        profile: Optional[MindscapeProfile] = None,
        active_intents: Optional[List[IntentCard]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """Execute agent using local LLM providers"""

        if not self.is_available():
            raise Exception("No LLM providers configured. Please set OPENAI_API_KEY or ANTHROPIC_API_KEY")

        # Build system prompt with context
        system_prompt = self.prompt_builder.build_system_prompt(
            agent_type, profile, active_intents or []
        )

        # Prepare messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task}
        ]

        # Get LLM provider and execute
        provider = self.llm_manager.get_provider()
        response_text = await provider.chat_completion(messages)

        # Build response
        return AgentResponse(
            execution_id="",  # Will be set by caller
            status="completed",
            output=response_text,
            used_profile=profile.dict() if profile else None,
            used_intents=[intent.dict() for intent in (active_intents or [])],
            metadata={
                "agent_type": agent_type,
                "backend": "local_llm",
                "provider": provider.__class__.__name__,
                **(metadata or {})
            }
        )

    def is_available(self) -> bool:
        """Check if any LLM provider is configured"""
        return len(self.llm_manager.get_available_providers()) > 0

    def get_backend_info(self) -> Dict[str, Any]:
        """Get backend information"""
        return {
            "type": "local_llm",
            "name": "Local LLM",
            "description": "Execute agents using local LLM providers (OpenAI, Anthropic)",
            "available": self.is_available(),
            "providers": self.llm_manager.get_available_providers()
        }
