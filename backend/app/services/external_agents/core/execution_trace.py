"""
Execution Trace Collector

Collects and structures execution traces from external agents
for integration with Mindscape's Asset Provenance system.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Represents a single tool call made by an external agent."""

    tool_name: str
    """Name of the tool that was called."""

    arguments: Dict[str, Any] = field(default_factory=dict)
    """Arguments passed to the tool."""

    result: Optional[str] = None
    """Result of the tool call (truncated if large)."""

    success: bool = True
    """Whether the tool call succeeded."""

    timestamp: Optional[str] = None
    """When the tool call was made."""

    duration_ms: Optional[int] = None
    """How long the tool call took in milliseconds."""


@dataclass
class FileChange:
    """Represents a file change made during execution."""

    path: str
    """Relative path within the sandbox."""

    change_type: str  # "created" | "modified" | "deleted"
    """Type of change."""

    size_bytes: Optional[int] = None
    """File size after change (None if deleted)."""

    content_hash: Optional[str] = None
    """SHA256 hash of content (for provenance)."""


@dataclass
class ExecutionTrace:
    """
    Complete execution trace for an external agent run.

    This trace is designed to integrate with Mindscape's Asset Provenance
    system, enabling:
    - Recording as a Take
    - Linking to Intent/Lens
    - Audit trail for governance
    """

    # Execution identity
    execution_id: str
    """Unique identifier for this execution."""

    agent_type: str = "openclaw"
    """Type of external agent (openclaw, autogpt, etc.)."""

    agent_version: Optional[str] = None
    """Version of the external agent."""

    # Timing
    started_at: str = ""
    """ISO timestamp when execution started."""

    completed_at: str = ""
    """ISO timestamp when execution completed."""

    duration_seconds: float = 0.0
    """Total execution duration."""

    # Governance context
    project_id: Optional[str] = None
    workspace_id: Optional[str] = None
    intent_id: Optional[str] = None
    lens_id: Optional[str] = None

    # Task info
    task_description: str = ""
    """The task that was executed."""

    task_hash: Optional[str] = None
    """Hash of the task description for deduplication."""

    # Execution details
    tool_calls: List[ToolCall] = field(default_factory=list)
    """List of tool calls made during execution."""

    file_changes: List[FileChange] = field(default_factory=list)
    """List of file changes made during execution."""

    # Result
    success: bool = True
    """Whether the execution succeeded."""

    output_summary: str = ""
    """Summary of the execution output."""

    error: Optional[str] = None
    """Error message if failed."""

    # Metadata
    sandbox_path: Optional[str] = None
    """Path to the sandbox directory."""

    config_snapshot: Optional[Dict[str, Any]] = None
    """Snapshot of the agent config used."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert nested dataclasses
        data["tool_calls"] = [asdict(tc) for tc in self.tool_calls]
        data["file_changes"] = [asdict(fc) for fc in self.file_changes]
        return data

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class ExecutionTraceCollector:
    """
    Collects execution traces and prepares them for Asset Provenance.

    Usage:
        collector = ExecutionTraceCollector(sandbox_path)
        trace = collector.collect_from_openclaw(response, request)
        await collector.save_trace(trace)
    """

    def __init__(self, sandbox_path: Path):
        """
        Initialize the trace collector.

        Args:
            sandbox_path: Path to the sandbox directory
        """
        self.sandbox_path = Path(sandbox_path)
        self.trace_dir = self.sandbox_path / ".mindscape" / "traces"

    def collect_from_response(
        self,
        response: "AgentResponse",  # noqa: F821 - forward reference
        request: "AgentRequest",  # noqa: F821 - forward reference
        agent_type: str = "unknown",
        execution_id: Optional[str] = None,
    ) -> ExecutionTrace:
        """
        Collect execution trace from a generic AgentResponse.

        Args:
            response: The AgentResponse from any adapter
            request: The original AgentRequest
            agent_type: Type of agent (e.g., 'openclaw', 'autogpt')
            execution_id: Optional custom execution ID

        Returns:
            ExecutionTrace ready for provenance storage
        """
        import hashlib
        import uuid

        if not execution_id:
            execution_id = f"exec_{uuid.uuid4().hex[:12]}"

        # Convert tool calls
        tool_calls = []
        for tc in response.tool_calls:
            if isinstance(tc, dict):
                tool_calls.append(
                    ToolCall(
                        tool_name=tc.get("tool", tc.get("name", "unknown")),
                        arguments=tc.get("arguments", tc.get("args", {})),
                        result=str(tc.get("result", ""))[:500],
                        success=tc.get("success", True),
                        timestamp=tc.get("timestamp"),
                        duration_ms=tc.get("duration_ms"),
                    )
                )

        # Convert file changes
        file_changes = []
        for path in response.files_created:
            file_changes.append(
                FileChange(
                    path=path,
                    change_type="created",
                    size_bytes=self._get_file_size(path),
                    content_hash=self._hash_file(path),
                )
            )
        for path in response.files_modified:
            file_changes.append(
                FileChange(
                    path=path,
                    change_type="modified",
                    size_bytes=self._get_file_size(path),
                    content_hash=self._hash_file(path),
                )
            )

        task_hash = hashlib.sha256(request.task.encode()).hexdigest()[:16]
        now = datetime.now().isoformat()

        return ExecutionTrace(
            execution_id=execution_id,
            agent_type=agent_type,
            started_at=now,
            completed_at=now,
            duration_seconds=response.duration_seconds,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            intent_id=request.intent_id,
            lens_id=request.lens_id,
            task_description=request.task,
            task_hash=task_hash,
            tool_calls=tool_calls,
            file_changes=file_changes,
            success=response.success,
            output_summary=response.output[:1000] if response.output else "",
            error=response.error,
            sandbox_path=request.sandbox_path,
        )

    def collect_from_openclaw(
        self,
        response: "AgentResponse",  # noqa: F821 - forward reference
        request: "AgentRequest",  # noqa: F821 - forward reference
        execution_id: Optional[str] = None,
    ) -> ExecutionTrace:
        """
        Collect execution trace from an OpenClaw response.

        Args:
            response: The AgentResponse from adapter
            request: The original AgentRequest
            execution_id: Optional custom execution ID

        Returns:
            ExecutionTrace ready for provenance storage
        """
        import hashlib
        import uuid

        # Generate execution ID if not provided
        if not execution_id:
            execution_id = f"exec_{uuid.uuid4().hex[:12]}"

        # Convert tool calls
        tool_calls = []
        for tc in response.tool_calls:
            if isinstance(tc, dict):
                tool_calls.append(
                    ToolCall(
                        tool_name=tc.get("tool", tc.get("name", "unknown")),
                        arguments=tc.get("arguments", tc.get("args", {})),
                        result=tc.get("result", "")[:500],  # Truncate
                        success=tc.get("success", True),
                        timestamp=tc.get("timestamp"),
                        duration_ms=tc.get("duration_ms"),
                    )
                )

        # Convert file changes
        file_changes = []
        for path in response.files_created:
            file_changes.append(
                FileChange(
                    path=path,
                    change_type="created",
                    size_bytes=self._get_file_size(path),
                    content_hash=self._hash_file(path),
                )
            )
        for path in response.files_modified:
            file_changes.append(
                FileChange(
                    path=path,
                    change_type="modified",
                    size_bytes=self._get_file_size(path),
                    content_hash=self._hash_file(path),
                )
            )

        # Calculate task hash
        task_hash = hashlib.sha256(request.task.encode()).hexdigest()[:16]

        now = datetime.now().isoformat()

        return ExecutionTrace(
            execution_id=execution_id,
            agent_type="openclaw",
            started_at=now,
            completed_at=now,
            duration_seconds=response.duration_seconds,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            intent_id=request.intent_id,
            lens_id=request.lens_id,
            task_description=request.task,
            task_hash=task_hash,
            tool_calls=tool_calls,
            file_changes=file_changes,
            success=response.success,
            output_summary=response.output[:1000] if response.output else "",
            error=response.error,
            sandbox_path=request.sandbox_path,
        )

    async def save_trace(self, trace: ExecutionTrace) -> Path:
        """
        Save execution trace to the sandbox.

        Args:
            trace: The execution trace to save

        Returns:
            Path to the saved trace file
        """
        self.trace_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{trace.execution_id}.json"
        trace_path = self.trace_dir / filename

        trace_path.write_text(trace.to_json())
        logger.info(f"Saved execution trace: {trace_path}")

        return trace_path

    async def load_trace(self, execution_id: str) -> Optional[ExecutionTrace]:
        """Load a previously saved execution trace."""
        trace_path = self.trace_dir / f"{execution_id}.json"

        if not trace_path.exists():
            return None

        try:
            data = json.loads(trace_path.read_text())

            # Reconstruct nested objects
            tool_calls = [ToolCall(**tc) for tc in data.pop("tool_calls", [])]
            file_changes = [FileChange(**fc) for fc in data.pop("file_changes", [])]

            return ExecutionTrace(
                **data,
                tool_calls=tool_calls,
                file_changes=file_changes,
            )
        except Exception as e:
            logger.error(f"Failed to load trace {execution_id}: {e}")
            return None

    def _get_file_size(self, rel_path: str) -> Optional[int]:
        """Get file size for a relative path."""
        try:
            full_path = self.sandbox_path / rel_path
            if full_path.exists():
                return full_path.stat().st_size
        except Exception:
            pass
        return None

    def _hash_file(self, rel_path: str) -> Optional[str]:
        """Calculate SHA256 hash of a file."""
        import hashlib

        try:
            full_path = self.sandbox_path / rel_path
            if full_path.exists() and full_path.stat().st_size < 10 * 1024 * 1024:
                # Only hash files under 10MB
                content = full_path.read_bytes()
                return hashlib.sha256(content).hexdigest()[:16]
        except Exception:
            pass
        return None


import uuid


class ExecutionTraceHandle:
    """Handle for an in-progress execution trace with lifecycle methods."""

    def __init__(self, trace_id: str, workspace_id: str, agent_id: str, task: str):
        self.trace_id = trace_id
        self.workspace_id = workspace_id
        self.agent_id = agent_id
        self.task = task
        self.started_at = datetime.utcnow().isoformat()
        self.status = "running"
        self.output: Optional[str] = None
        self.error: Optional[str] = None
        self.artifacts: List[str] = []

    def complete(
        self,
        success: bool = True,
        output: str = "",
        artifacts: Optional[List[str]] = None,
    ):
        """Mark the trace as completed."""
        self.status = "completed" if success else "failed"
        self.output = output
        self.artifacts = artifacts or []
        logger.info(
            f"[ExecutionTrace] Trace {self.trace_id} completed: "
            f"success={success}, artifacts={len(self.artifacts)}"
        )

    def fail(self, error: str):
        """Mark the trace as failed."""
        self.status = "failed"
        self.error = error
        logger.warning(f"[ExecutionTrace] Trace {self.trace_id} failed: {error}")


class ExecutionTraceService:
    """Service for creating and managing execution traces."""

    def start_trace(
        self,
        workspace_id: str,
        agent_id: str,
        task: str,
    ) -> ExecutionTraceHandle:
        """Start a new execution trace and return a handle for it."""
        trace_id = str(uuid.uuid4())
        logger.info(
            f"[ExecutionTrace] Starting trace {trace_id}: "
            f"agent={agent_id}, workspace={workspace_id}"
        )
        return ExecutionTraceHandle(
            trace_id=trace_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            task=task,
        )
