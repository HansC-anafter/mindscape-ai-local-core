from .base import *


@dataclass
class ExecutionContext:
    """Parsed context from a dispatch payload."""

    execution_id: str
    workspace_id: str
    task: str
    allowed_tools: List[str]
    max_duration: int
    model: str = ""
    project_id: str = ""
    intent_id: str = ""
    lens_id: str = ""
    sandbox_path: str = ""
    issued_at: str = ""
    conversation_context: str = ""
    thread_id: str = ""
    auth_workspace_id: str = ""
    source_workspace_id: str = ""
    control_action: str = ""
    uploaded_files: List[Dict[str, Any]] = field(default_factory=list)
    recommended_pack_codes: List[str] = field(default_factory=list)
    file_hint: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dispatch(cls, msg: Dict[str, Any]) -> "ExecutionContext":
        """Parse a dispatch payload into an ExecutionContext."""
        ctx = msg.get("context", {})
        return cls(
            execution_id=msg.get("execution_id", ""),
            workspace_id=msg.get("workspace_id", ""),
            task=msg.get("task", ""),
            allowed_tools=msg.get("allowed_tools", []),
            max_duration=msg.get("max_duration", DEFAULT_TASK_TIMEOUT),
            model=msg.get("model", "") or "",
            project_id=ctx.get("project_id", ""),
            intent_id=ctx.get("intent_id", ""),
            lens_id=ctx.get("lens_id", ""),
            sandbox_path=ctx.get("sandbox_path", ""),
            issued_at=msg.get("issued_at", ""),
            conversation_context=ctx.get("conversation_context", ""),
            thread_id=ctx.get("thread_id", ""),
            auth_workspace_id=ctx.get("auth_workspace_id", ""),
            source_workspace_id=ctx.get("source_workspace_id", ""),
            control_action=ctx.get("control_action", ""),
            uploaded_files=ctx.get("uploaded_files", []),
            recommended_pack_codes=ctx.get("recommended_pack_codes", []),
            file_hint=ctx.get("file_hint", ""),
            inputs=ctx.get("inputs", {}) if isinstance(ctx.get("inputs", {}), dict) else {},
        )


@dataclass
class ExecutionResult:
    """Result of a task execution."""

    status: str = "completed"
    output: str = ""
    error: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "tool_calls": self.tool_calls,
            "files_modified": self.files_modified,
            "files_created": self.files_created,
        }
        if self.attachments:
            payload["attachments"] = self.attachments
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


# Type for progress callback: async fn(execution_id, percent, message)
ProgressCallback = Callable[[str, int, str], Coroutine[Any, Any, None]]
