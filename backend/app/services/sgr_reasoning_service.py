"""
SGR (Self-Graph Reasoning) Service

Middleware service that injects reasoning graph extraction into the LLM pipeline.
Supports two modes:
    - INLINE: Single LLM call with reasoning graph in the response
    - TWO_PASS: Separate LLM call to extract reasoning from existing response

The service persists reasoning traces and integrates with MindscapeGraphService
for graph visualization.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.models.reasoning_trace import (
    ReasoningEdge,
    ReasoningGraph,
    ReasoningNode,
    ReasoningTrace,
    SGRMode,
)
from app.services.stores.reasoning_traces_store import ReasoningTracesStore

logger = logging.getLogger(__name__)

# Pattern to extract ```reasoning_graph``` fenced code blocks
_REASONING_BLOCK_RE = re.compile(
    r"```reasoning_graph\s*\n(.*?)\n\s*```",
    re.DOTALL,
)


class SGRReasoningService:
    """
    SGR reasoning middleware.

    Responsibilities:
    1. Inject SGR system instruction into LLM messages (inline mode)
    2. Parse reasoning graph from LLM response
    3. Persist reasoning trace to database
    4. Strip reasoning block from user-facing response text
    """

    def __init__(self):
        self._store = ReasoningTracesStore()

    # ========== Prompt Injection ==========

    def inject_sgr_prompt(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Inject SGR system instruction into the message list (inline mode).

        Prepends or appends the SGR instruction to the system message.
        Returns a new list (does not mutate original).
        """
        from app.services.sgr_prompts import SGR_SYSTEM_INSTRUCTION

        injected = list(messages)

        # Find existing system message
        system_idx = next(
            (i for i, m in enumerate(injected) if m.get("role") == "system"),
            None,
        )

        if system_idx is not None:
            # Append SGR instruction to existing system message
            original_content = injected[system_idx].get("content", "")
            injected[system_idx] = {
                **injected[system_idx],
                "content": f"{original_content}\n\n{SGR_SYSTEM_INSTRUCTION}",
            }
        else:
            # Prepend new system message
            injected.insert(0, {"role": "system", "content": SGR_SYSTEM_INSTRUCTION})

        return injected

    # ========== Response Parsing ==========

    def parse_reasoning_graph(
        self, response_text: str
    ) -> Tuple[Optional[ReasoningGraph], str]:
        """
        Extract reasoning graph from LLM response text.

        Returns:
            Tuple of (ReasoningGraph or None, cleaned response text)
            The cleaned text has the ```reasoning_graph``` block removed.
        """
        match = _REASONING_BLOCK_RE.search(response_text)
        if not match:
            return None, response_text

        try:
            graph_json = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse reasoning graph JSON: {e}")
            return None, response_text

        # Validate minimal structure
        if not isinstance(graph_json.get("nodes"), list):
            logger.warning("Reasoning graph has no valid 'nodes' array")
            return None, response_text

        graph = ReasoningGraph.from_dict(graph_json)

        # Strip the reasoning block from user-facing text
        cleaned = _REASONING_BLOCK_RE.sub("", response_text).strip()

        # If the graph has an answer, prefer it as the final text
        if graph.answer and not cleaned:
            cleaned = graph.answer

        return graph, cleaned

    # ========== Persistence ==========

    def persist_trace(
        self,
        workspace_id: str,
        graph: ReasoningGraph,
        sgr_mode: SGRMode = SGRMode.INLINE,
        execution_id: Optional[str] = None,
        assistant_event_id: Optional[str] = None,
        meeting_session_id: Optional[str] = None,
        model: Optional[str] = None,
        token_count: Optional[int] = None,
        latency_ms: Optional[int] = None,
    ) -> ReasoningTrace:
        """Persist a reasoning trace to the database."""
        trace = ReasoningTrace.new(
            workspace_id=workspace_id,
            graph=graph,
            sgr_mode=sgr_mode,
            execution_id=execution_id,
            assistant_event_id=assistant_event_id,
            meeting_session_id=meeting_session_id,
            model=model,
            token_count=token_count,
            latency_ms=latency_ms,
        )
        self._store.create(trace)
        logger.info(
            f"Persisted reasoning trace {trace.id} "
            f"({len(graph.nodes)} nodes, {len(graph.edges)} edges)"
        )
        return trace

    # ========== Full Processing Pipeline ==========

    def process_response(
        self,
        response_text: str,
        workspace_id: str,
        sgr_mode: SGRMode = SGRMode.INLINE,
        execution_id: Optional[str] = None,
        assistant_event_id: Optional[str] = None,
        meeting_session_id: Optional[str] = None,
        model: Optional[str] = None,
        token_count: Optional[int] = None,
        latency_ms: Optional[int] = None,
    ) -> Tuple[str, Optional[str]]:
        """
        Full SGR processing pipeline: parse -> persist -> clean.

        Args:
            response_text: Raw LLM response text (may contain reasoning_graph block)
            workspace_id: Workspace ID for persistence
            sgr_mode: Inline or two-pass
            execution_id: Optional execution context ID
            assistant_event_id: Optional event ID for linking
            meeting_session_id: Optional meeting session ID for linking
            model: LLM model name
            token_count: Token usage
            latency_ms: LLM call latency

        Returns:
            Tuple of (cleaned_response_text, reasoning_trace_id or None)
        """
        graph, cleaned_text = self.parse_reasoning_graph(response_text)

        if graph is None:
            return response_text, None

        trace = self.persist_trace(
            workspace_id=workspace_id,
            graph=graph,
            sgr_mode=sgr_mode,
            execution_id=execution_id,
            assistant_event_id=assistant_event_id,
            meeting_session_id=meeting_session_id,
            model=model,
            token_count=token_count,
            latency_ms=latency_ms,
        )

        return cleaned_text, trace.id

    # ========== Backfill (post-creation updates) ==========

    def backfill_event_id(self, trace_id: str, event_id: str) -> None:
        """Backfill assistant_event_id to an existing trace (B1 flow: SGR first, event second)."""
        self._store.update_field(trace_id, "assistant_event_id", event_id)
        logger.info(f"Backfilled assistant_event_id={event_id} to trace {trace_id}")

    def backfill_execution_id(self, trace_id: str, execution_id: str) -> None:
        """Backfill execution_id to an existing trace (Hybrid mode: execution created after SGR)."""
        self._store.update_field(trace_id, "execution_id", execution_id)
        logger.info(f"Backfilled execution_id={execution_id} to trace {trace_id}")
