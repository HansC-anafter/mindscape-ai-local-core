"""
Runtime Port - Abstract interface for playbook execution runtime

Defines the interface that all runtime implementations must follow,
enabling pluggable runtime backends (Simple, LangGraph, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from backend.app.models.playbook import PlaybookRun
    from backend.app.core.execution_context import ExecutionContext


class ExecutionProfile(BaseModel):
    """Execution profile for playbook runtime selection"""

    execution_mode: str = Field(
        default="simple",
        description="Execution mode: 'simple' | 'durable'"
    )
    supports_resume: bool = Field(
        default=False,
        description="Whether execution can be resumed from checkpoint"
    )
    requires_human_approval: bool = Field(
        default=False,
        description="Whether execution requires human approval at checkpoints"
    )
    retry_policy: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Retry policy configuration"
    )
    timeout: Optional[int] = Field(
        default=None,
        description="Execution timeout in seconds"
    )
    side_effect_level: str = Field(
        default="none",
        description="Side effect level: 'none' | 'low' | 'high'"
    )
    required_capabilities: list[str] = Field(
        default_factory=lambda: [],
        description="Required runtime capabilities"
    )

    class Config:
        json_encoders = {
            dict: lambda v: v
        }


class ExecutionResult(BaseModel):
    """Execution result from runtime"""

    status: str = Field(
        ...,
        description="Execution status: 'completed' | 'failed' | 'paused' | 'running'"
    )
    execution_id: str = Field(
        ...,
        description="Execution ID"
    )
    outputs: Dict[str, Any] = Field(
        default_factory=lambda: {},
        description="Execution outputs"
    )
    checkpoint: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Checkpoint data for resume"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if execution failed"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {},
        description="Additional metadata"
    )

    class Config:
        json_encoders = {
            dict: lambda v: v
        }


class RuntimePort(ABC):
    """Abstract interface for playbook execution runtime"""

    @abstractmethod
    async def execute(
        self,
        playbook_run: "PlaybookRun",
        context: "ExecutionContext",
        inputs: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        Execute playbook with this runtime

        Args:
            playbook_run: PlaybookRun instance (playbook.md + playbook.json)
            context: ExecutionContext with actor_id, workspace_id, etc.
            inputs: Optional input parameters

        Returns:
            ExecutionResult with status, outputs, checkpoint, etc.
        """
        pass

    @abstractmethod
    def supports(self, execution_profile: ExecutionProfile) -> bool:
        """
        Check if this runtime supports the execution profile

        Args:
            execution_profile: ExecutionProfile to check

        Returns:
            True if this runtime supports the profile, False otherwise
        """
        pass

    @abstractmethod
    async def resume(
        self,
        execution_id: str,
        checkpoint: Dict[str, Any]
    ) -> ExecutionResult:
        """
        Resume execution from checkpoint

        Args:
            execution_id: Execution ID
            checkpoint: Checkpoint data from previous execution

        Returns:
            ExecutionResult with resumed execution state
        """
        pass

    @abstractmethod
    async def pause(
        self,
        execution_id: str
    ) -> ExecutionResult:
        """
        Pause execution and create checkpoint

        Args:
            execution_id: Execution ID to pause

        Returns:
            ExecutionResult with checkpoint data
        """
        pass

    @abstractmethod
    async def cancel(
        self,
        execution_id: str,
        reason: Optional[str] = None
    ) -> ExecutionResult:
        """
        Cancel execution

        Args:
            execution_id: Execution ID to cancel
            reason: Optional cancellation reason

        Returns:
            ExecutionResult with cancellation status
        """
        pass

    @abstractmethod
    async def get_status(
        self,
        execution_id: str
    ) -> ExecutionResult:
        """
        Get execution status

        Args:
            execution_id: Execution ID

        Returns:
            ExecutionResult with current status
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Runtime name

        Returns:
            Runtime name (e.g., 'simple', 'langgraph')
        """
        pass

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """
        Runtime capabilities

        Returns:
            List of capability strings this runtime supports
        """
        pass
