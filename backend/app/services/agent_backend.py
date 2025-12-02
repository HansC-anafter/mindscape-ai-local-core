"""
Agent Backend Interface
Abstract interface for different agent execution backends
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from backend.app.models.mindscape import MindscapeProfile, IntentCard, AgentResponse


class AgentBackend(ABC):
    """Abstract base class for agent execution backends"""

    @abstractmethod
    async def run_agent(
        self,
        task: str,
        agent_type: str,
        profile: Optional[MindscapeProfile] = None,
        active_intents: Optional[List[IntentCard]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """
        Execute an agent task

        Args:
            task: Task description
            agent_type: Type of agent (planner, writer, coach, coder)
            profile: User profile context
            active_intents: List of active intent cards
            metadata: Additional metadata

        Returns:
            AgentResponse with execution results
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available/configured"""
        raise NotImplementedError

    @abstractmethod
    def get_backend_info(self) -> Dict[str, Any]:
        """Get backend information"""
        raise NotImplementedError
