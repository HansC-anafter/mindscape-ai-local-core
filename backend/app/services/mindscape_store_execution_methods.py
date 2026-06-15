from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import (
    AgentExecution,
    Entity,
    EntityTag,
    EntityType,
    EventActor,
    EventType,
    IntentCard,
    IntentLog,
    IntentStatus,
    MindEvent,
    MindscapeProfile,
    PriorityLevel,
    Tag,
    TagCategory,
)
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store_utils import _utc_now


class MindscapeStoreAgentExecutionMixin:
    def create_agent_execution(self, execution: AgentExecution) -> AgentExecution:
        """Create a new agent execution record"""
        return self.agent_executions.create_agent_execution(execution)

    def get_agent_execution(self, execution_id: str) -> Optional[AgentExecution]:
        """Get agent execution by ID"""
        return self.agent_executions.get_agent_execution(execution_id)

    def list_agent_executions(
        self, profile_id: str, limit: int = 50
    ) -> List[AgentExecution]:
        """List recent agent executions for a profile"""
        return self.agent_executions.list_agent_executions(profile_id, limit=limit)
