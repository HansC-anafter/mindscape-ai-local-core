"""
Trace Recorder

Records execution steps as trace nodes and edges.
Integrates with existing services to automatically capture LLM calls, tool executions, policy decisions, etc.
"""

import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, List, Optional, Any
from threading import Lock

from .trace_schema import (
    TraceNode,
    TraceNodeType,
    TraceEdge,
    TraceEdgeType,
    TraceGraph,
    TraceMetadata,
    TraceStatus,
)

logger = logging.getLogger(__name__)


class TraceContext:
    """Context for a single trace session"""
    def __init__(self, trace_id: str, workspace_id: str, execution_id: str, user_id: Optional[str] = None):
        self.trace_id = trace_id
        self.workspace_id = workspace_id
        self.execution_id = execution_id
        self.user_id = user_id
        self.current_node_id: Optional[str] = None
        self.node_stack: List[str] = []  # Stack for nested nodes


class TraceRecorder:
    """
    Records trace nodes and edges for execution steps.

    Thread-safe and supports nested trace recording.
    """

    def __init__(self):
        self._traces: Dict[str, TraceGraph] = {}
        self._contexts: Dict[str, TraceContext] = {}
        self._lock = Lock()

    def create_trace(
        self,
        workspace_id: str,
        execution_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> str:
        """Create a new trace graph"""
        if trace_id is None:
            trace_id = str(uuid.uuid4())

        with self._lock:
            trace_graph = TraceGraph(trace_id=trace_id)
            self._traces[trace_id] = trace_graph
            self._contexts[trace_id] = TraceContext(
                trace_id=trace_id,
                workspace_id=workspace_id,
                execution_id=execution_id,
                user_id=user_id,
            )

        logger.debug(f"TraceRecorder: Created trace {trace_id} for execution {execution_id}")
        return trace_id

    def start_node(
        self,
        trace_id: str,
        node_type: TraceNodeType,
        name: str,
        parent_node_id: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start recording a new trace node"""
        node_id = str(uuid.uuid4())
        context = self._contexts.get(trace_id)

        if not context:
            logger.warning(f"TraceRecorder: Trace {trace_id} not found")
            return node_id

        trace_graph = self._traces.get(trace_id)
        if not trace_graph:
            logger.warning(f"TraceRecorder: Trace graph {trace_id} not found")
            return node_id

        with self._lock:
            # Create metadata
            trace_metadata = TraceMetadata(
                workspace_id=context.workspace_id,
                execution_id=context.execution_id,
                user_id=context.user_id,
                custom_metadata=metadata or {},
            )

            # Create node
            node = TraceNode(
                node_id=node_id,
                node_type=node_type,
                name=name,
                status=TraceStatus.RUNNING,
                start_time=_utc_now(),
                metadata=trace_metadata,
                input_data=input_data,
            )

            trace_graph.nodes.append(node)

            # Set root node if this is the first node
            if trace_graph.root_node_id is None:
                trace_graph.root_node_id = node_id

            # Create edge to parent if specified
            if parent_node_id:
                edge = TraceEdge(
                    edge_id=str(uuid.uuid4()),
                    source_node_id=parent_node_id,
                    target_node_id=node_id,
                    edge_type=TraceEdgeType.SEQUENTIAL,
                )
                trace_graph.edges.append(edge)
            elif context.current_node_id:
                # Auto-link to current node
                edge = TraceEdge(
                    edge_id=str(uuid.uuid4()),
                    source_node_id=context.current_node_id,
                    target_node_id=node_id,
                    edge_type=TraceEdgeType.SEQUENTIAL,
                )
                trace_graph.edges.append(edge)

            # Update context
            if context.current_node_id:
                context.node_stack.append(context.current_node_id)
            context.current_node_id = node_id

        logger.debug(f"TraceRecorder: Started node {node_id} ({node_type.value}) in trace {trace_id}")
        return node_id

    def end_node(
        self,
        trace_id: str,
        node_id: str,
        status: TraceStatus = TraceStatus.SUCCESS,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        error_stack: Optional[str] = None,
        cost_tokens: Optional[int] = None,
        latency_ms: Optional[int] = None,
    ):
        """End recording a trace node"""
        trace_graph = self._traces.get(trace_id)
        context = self._contexts.get(trace_id)

        if not trace_graph or not context:
            logger.warning(f"TraceRecorder: Trace {trace_id} not found")
            return

        with self._lock:
            node = trace_graph.get_node(node_id)
            if not node:
                logger.warning(f"TraceRecorder: Node {node_id} not found in trace {trace_id}")
                return

            node.status = status
            node.end_time = _utc_now()
            if output_data:
                node.output_data = output_data

            # Update metadata
            if node.metadata:
                if error_message:
                    node.metadata.error_message = error_message
                if error_stack:
                    node.metadata.error_stack = error_stack
                if cost_tokens:
                    node.metadata.cost_tokens = cost_tokens
                if latency_ms:
                    node.metadata.latency_ms = latency_ms

            # Restore parent node from stack
            if context.node_stack:
                context.current_node_id = context.node_stack.pop()
            else:
                context.current_node_id = None

        logger.debug(f"TraceRecorder: Ended node {node_id} with status {status.value} in trace {trace_id}")

    @contextmanager
    def trace_node(
        self,
        trace_id: str,
        node_type: TraceNodeType,
        name: str,
        parent_node_id: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Context manager for tracing a node"""
        node_id = self.start_node(
            trace_id=trace_id,
            node_type=node_type,
            name=name,
            parent_node_id=parent_node_id,
            input_data=input_data,
            metadata=metadata,
        )

        status = TraceStatus.SUCCESS
        error_message = None
        error_stack = None
        output_data = None

        try:
            yield node_id
        except Exception as e:
            status = TraceStatus.FAILED
            error_message = str(e)
            import traceback
            error_stack = traceback.format_exc()
            raise
        finally:
            self.end_node(
                trace_id=trace_id,
                node_id=node_id,
                status=status,
                output_data=output_data,
                error_message=error_message,
                error_stack=error_stack,
            )

    def add_edge(
        self,
        trace_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: TraceEdgeType = TraceEdgeType.SEQUENTIAL,
        label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Add an edge between two nodes"""
        trace_graph = self._traces.get(trace_id)
        if not trace_graph:
            logger.warning(f"TraceRecorder: Trace {trace_id} not found")
            return

        with self._lock:
            edge = TraceEdge(
                edge_id=str(uuid.uuid4()),
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                edge_type=edge_type,
                label=label,
                metadata=metadata or {},
            )
            trace_graph.edges.append(edge)

        logger.debug(f"TraceRecorder: Added edge {edge.edge_id} in trace {trace_id}")

    def get_trace(self, trace_id: str) -> Optional[TraceGraph]:
        """Get a trace graph by ID"""
        return self._traces.get(trace_id)

    def list_traces(self, workspace_id: Optional[str] = None) -> List[TraceGraph]:
        """List all traces, optionally filtered by workspace"""
        traces = list(self._traces.values())
        if workspace_id:
            traces = [
                t for t in traces
                if t.nodes and t.nodes[0].metadata and t.nodes[0].metadata.workspace_id == workspace_id
            ]
        return traces

    def delete_trace(self, trace_id: str) -> bool:
        """Delete a trace"""
        with self._lock:
            if trace_id in self._traces:
                del self._traces[trace_id]
            if trace_id in self._contexts:
                del self._contexts[trace_id]
                logger.debug(f"TraceRecorder: Deleted trace {trace_id}")
                return True
            return False


# Global trace recorder instance
_global_recorder: Optional[TraceRecorder] = None


def get_trace_recorder() -> TraceRecorder:
    """Get the global trace recorder instance"""
    global _global_recorder
    if _global_recorder is None:
        _global_recorder = TraceRecorder()
    return _global_recorder

