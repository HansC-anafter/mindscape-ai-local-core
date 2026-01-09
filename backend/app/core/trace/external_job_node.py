"""
ExternalJob Node Schema

P0-8: External workflow node (minimal observable model for external workflows not executed via MCP)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
import uuid

from backend.app.core.trace.trace_schema import TraceNode, TraceNodeType, TraceStatus


@dataclass
class ExternalJobNode(TraceNode):
    """
    External workflow node

    P0-8 hard rule: Used to represent external workflows not executed via MCP (n8n / Zapier / Make, etc.)
    """
    # Override node_type
    node_type: TraceNodeType = TraceNodeType.EXTERNAL_JOB

    # External system identification
    tool_name: str = ""  # e.g., "n8n", "zapier", "slack", "notion"
    external_job_id: str = ""  # External system's job ID
    external_run_id: Optional[str] = None  # External system's run ID (if available)

    # Deep link (don't store logs, but store "where to view")
    deep_link_to_external_log: Optional[str] = None  # e.g., "https://n8n.io/workflow/123/execution/456"

    # Status tracking
    retry_count: int = 0

    # Output fingerprint (don't store raw payload, only hash)
    output_fingerprint: Optional[str] = None  # hash / key_fields_hash
    output_fingerprint_type: str = "sha256"  # Hash algorithm

    # Optional: Key fields hash (if external system supports structured output)
    key_fields_hash_map: Optional[Dict[str, str]] = None

    def __post_init__(self):
        """Post-initialization processing"""
        # Ensure node_type is EXTERNAL_JOB
        if self.node_type != TraceNodeType.EXTERNAL_JOB:
            self.node_type = TraceNodeType.EXTERNAL_JOB

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        result = super().to_dict()
        result.update({
            "tool_name": self.tool_name,
            "external_job_id": self.external_job_id,
            "external_run_id": self.external_run_id,
            "deep_link_to_external_log": self.deep_link_to_external_log,
            "retry_count": self.retry_count,
            "output_fingerprint": self.output_fingerprint,
            "output_fingerprint_type": self.output_fingerprint_type,
            "key_fields_hash_map": self.key_fields_hash_map,
        })
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExternalJobNode":
        """Deserialize from dictionary"""
        # First create base TraceNode
        base_node = TraceNode.from_dict(data)

        return cls(
            node_id=base_node.node_id,
            node_type=TraceNodeType.EXTERNAL_JOB,
            name=base_node.name,
            status=base_node.status,
            start_time=base_node.start_time,
            end_time=base_node.end_time,
            metadata=base_node.metadata,
            input_data=base_node.input_data,
            output_data=base_node.output_data,
            version=base_node.version,
            tool_name=data.get("tool_name", ""),
            external_job_id=data.get("external_job_id", ""),
            external_run_id=data.get("external_run_id"),
            deep_link_to_external_log=data.get("deep_link_to_external_log"),
            retry_count=data.get("retry_count", 0),
            output_fingerprint=data.get("output_fingerprint"),
            output_fingerprint_type=data.get("output_fingerprint_type", "sha256"),
            key_fields_hash_map=data.get("key_fields_hash_map"),
        )

    @classmethod
    def create(
        cls,
        tool_name: str,
        external_job_id: str,
        name: Optional[str] = None,
        external_run_id: Optional[str] = None,
        deep_link: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> "ExternalJobNode":
        """
        Create ExternalJob node

        Args:
            tool_name: Tool name (e.g., "n8n")
            external_job_id: External system's job ID
            name: Node name (optional, defaults to tool_name)
            external_run_id: External system's run ID (optional)
            deep_link: Deep link URL (optional)
            span_id: Span ID (optional, for attaching to span)

        Returns:
            ExternalJobNode
        """
        node_id = span_id or str(uuid.uuid4())

        return cls(
            node_id=node_id,
            node_type=TraceNodeType.EXTERNAL_JOB,
            name=name or tool_name,
            status=TraceStatus.PENDING,
            start_time=datetime.utcnow(),
            tool_name=tool_name,
            external_job_id=external_job_id,
            external_run_id=external_run_id,
            deep_link_to_external_log=deep_link,
        )

