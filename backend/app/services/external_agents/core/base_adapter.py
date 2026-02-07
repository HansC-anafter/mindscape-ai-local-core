"""
Base Agent Adapter

Abstract base class for all external agent adapters.
Each agent implementation must extend this class.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentRequest:
    """
    Generic request for external agent execution.

    This is the common interface used by the Playbook engine.
    Agent-specific adapters may have additional fields.
    """

    task: str
    """The task description for the agent to execute."""

    sandbox_path: str
    """Path to the isolated sandbox directory."""

    allowed_tools: List[str] = field(default_factory=lambda: ["file", "web_search"])
    """List of allowed tools/skills."""

    denied_tools: List[str] = field(default_factory=list)
    """List of explicitly denied tools."""

    max_duration_seconds: int = 300
    """Maximum execution time in seconds."""

    # Mindscape governance context
    project_id: Optional[str] = None
    workspace_id: Optional[str] = None
    intent_id: Optional[str] = None
    lens_id: Optional[str] = None

    # Agent-specific configuration
    agent_config: Dict[str, Any] = field(default_factory=dict)
    """Additional agent-specific configuration."""


@dataclass
class AgentResponse:
    """
    Generic response from external agent execution.
    """

    success: bool
    """Whether the execution completed successfully."""

    output: str
    """The output from the agent."""

    duration_seconds: float
    """How long the execution took."""

    # Execution trace for Asset Provenance
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    """List of tool calls made during execution."""

    files_modified: List[str] = field(default_factory=list)
    """List of files modified during execution."""

    files_created: List[str] = field(default_factory=list)
    """List of files created during execution."""

    error: Optional[str] = None
    """Error message if execution failed."""

    exit_code: int = 0
    """Process exit code."""

    # Agent-specific metadata
    agent_metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional agent-specific metadata."""


class BaseAgentAdapter(ABC):
    """
    Abstract base class for external agent adapters.

    Each external agent should have an adapter that extends this class.

    Responsibilities:
    1. Check if the agent is available on the system
    2. Execute tasks within the sandbox
    3. Collect execution traces for governance
    """

    # Override in subclass
    AGENT_NAME: str = "base"
    AGENT_VERSION: str = "0.0.0"

    # Default tools that are always denied for security
    ALWAYS_DENIED_TOOLS: List[str] = [
        "system.run",
        "gateway",
        "docker",
    ]

    def __init__(self):
        """Initialize the adapter."""
        self._version_cache: Optional[str] = None
        self._available_cache: Optional[bool] = None

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if this agent is installed and accessible.

        Returns:
            True if the agent can be used, False otherwise.
        """
        pass

    @abstractmethod
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """
        Execute a task using this agent.

        Args:
            request: The execution request with task and constraints.

        Returns:
            AgentResponse with results and execution trace.
        """
        pass

    def get_version(self) -> Optional[str]:
        """Get the cached agent version string."""
        return self._version_cache

    def get_agent_info(self) -> Dict[str, Any]:
        """Get agent information for registration."""
        return {
            "name": self.AGENT_NAME,
            "version": self.AGENT_VERSION,
            "installed_version": self._version_cache,
            "always_denied_tools": self.ALWAYS_DENIED_TOOLS,
        }

    def merge_denied_tools(self, request_denied: List[str]) -> List[str]:
        """Merge request-denied tools with always-denied tools."""
        return list(set(self.ALWAYS_DENIED_TOOLS + request_denied))

    def validate_sandbox_path(self, sandbox_path: str) -> bool:
        """
        Validate that the sandbox path is safe.

        Args:
            sandbox_path: Path to validate.

        Returns:
            True if the path is safe, False otherwise.
        """
        # Must be absolute
        if not sandbox_path.startswith("/"):
            return False

        # Cannot be system directories
        forbidden_prefixes = [
            "/etc",
            "/usr",
            "/bin",
            "/sbin",
            "/var",
            "/root",
            "/home",
            "/System",
            "/Library",
        ]

        for prefix in forbidden_prefixes:
            if sandbox_path.startswith(prefix):
                return False

        return True

    def log_execution_start(self, request: AgentRequest) -> None:
        """Log the start of an execution."""
        logger.info(
            f"[{self.AGENT_NAME}] Starting execution",
            extra={
                "task_preview": request.task[:100],
                "sandbox_path": request.sandbox_path,
                "allowed_tools": request.allowed_tools,
            },
        )

    def log_execution_end(self, response: AgentResponse) -> None:
        """Log the end of an execution."""
        logger.info(
            f"[{self.AGENT_NAME}] Execution completed",
            extra={
                "success": response.success,
                "duration": response.duration_seconds,
                "files_created": len(response.files_created),
                "files_modified": len(response.files_modified),
            },
        )
