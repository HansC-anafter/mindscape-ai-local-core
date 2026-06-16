"""
Agent Runner Service
Handles AI agent execution with user context and mindscape integration
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import (
    AgentExecution,
    AgentResponse,
    MindscapeProfile,
    RunAgentRequest,
)
from backend.app.services.agent_runner_catalog import (
    get_agent_detail as _get_agent_detail,
    get_available_agents as _get_available_agents,
)
from backend.app.services.agent_runner_execution import (
    run_agent as _run_agent,
    run_agents_parallel as _run_agents_parallel,
)
from backend.app.services.agent_runner_habits import (
    extract_seeds_from_execution as _extract_seeds_from_execution,
    observe_habits_from_execution as _observe_habits_from_execution,
)
from backend.app.services.agent_runner_prompt_builder import AgentPromptBuilder
from backend.app.services.agent_runner_scene import suggest_work_scene as _suggest_work_scene
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.shared.llm_utils import build_prompt, call_llm

from backend.app.services.llm_providers import (
    AnthropicProvider,
    LLMProvider,
    LLMProviderManager,
    LlamaCppProvider,
    OllamaProvider,
    OpenAIProvider,
    VertexAIProvider,
)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class AgentRunner:
    """Main agent execution service."""

    def __init__(self):
        self.store = MindscapeStore()
        self._llm_manager = None
        self.prompt_builder = AgentPromptBuilder()
        self._backend_manager = None

    @property
    def llm_manager(self):
        """Lazily initialize the provider manager to avoid request-path init spam."""
        if self._llm_manager is None:
            from backend.app.shared.llm_provider_helper import create_llm_provider_manager

            self._llm_manager = create_llm_provider_manager()
        return self._llm_manager

    @property
    def backend_manager(self):
        """Lazy initialization of backend manager."""
        if self._backend_manager is None:
            from backend.app.services.backend_manager import BackendManager

            self._backend_manager = BackendManager(self.store)
        return self._backend_manager

    async def run_agent(
        self, profile_id: str, request: RunAgentRequest
    ) -> AgentResponse:
        """Execute an agent with the given request."""
        return await _run_agent(self, profile_id, request)

    async def get_execution_status(self, execution_id: str) -> Optional[AgentExecution]:
        """Get execution status by ID."""
        return self.store.get_agent_execution(execution_id)

    async def list_executions(
        self, profile_id: str, limit: int = 20
    ) -> List[AgentExecution]:
        """List recent executions for a profile."""
        return self.store.list_agent_executions(profile_id, limit)

    def get_available_agents(self) -> List[Dict[str, Any]]:
        """Get list of available agent types."""
        return _get_available_agents()

    def get_agent_detail(self, agent_type: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific agent type."""
        return _get_agent_detail(agent_type)

    def get_available_providers(self) -> List[str]:
        """Get list of available LLM providers."""
        return self.llm_manager.get_available_providers()

    async def run_agents_parallel(
        self,
        profile_id: str,
        task: str,
        agent_types: List[str],
        use_mindscape: bool = True,
        intent_ids: List[str] = None,
    ) -> List[AgentResponse]:
        """Run multiple agents in parallel for the same task."""
        return await _run_agents_parallel(
            self,
            profile_id=profile_id,
            task=task,
            agent_types=agent_types,
            use_mindscape=use_mindscape,
            intent_ids=intent_ids,
        )

    async def suggest_work_scene(self, profile_id: str, task: str) -> Dict[str, Any]:
        """Use LLM to suggest the best work scene for a given task."""
        return await _suggest_work_scene(
            profile_id=profile_id,
            task=task,
            llm_provider=self.llm_manager,
            build_prompt_func=build_prompt,
            call_llm_func=call_llm,
        )

    async def _extract_seeds_from_execution(
        self,
        profile_id: str,
        execution_id: str,
        task: str,
        output: Optional[str] = None,
    ):
        """Extract seeds from execution."""
        return await _extract_seeds_from_execution(
            profile_id=profile_id,
            execution_id=execution_id,
            task=task,
            output=output,
        )

    async def _observe_habits_from_execution(
        self,
        profile_id: str,
        execution: AgentExecution,
        profile: Optional[MindscapeProfile] = None,
    ):
        """Observe habits from agent execution and generate candidates if needed."""
        return await _observe_habits_from_execution(
            self,
            profile_id=profile_id,
            execution=execution,
            profile=profile,
        )
