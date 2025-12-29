"""
Tool Call Chain Tracker - Track tool call chains for policy enforcement

Phase 2: Enforces max_tool_call_chain limit from Runtime Profile.
"""

from typing import Dict, List, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class ToolCallChainTracker:
    """
    Track tool call chains for a single execution session

    Used to enforce max_tool_call_chain policy from Runtime Profile.
    """

    def __init__(self, execution_id: str):
        """
        Initialize chain tracker for an execution

        Args:
            execution_id: Execution ID (unique per execution session)
        """
        self.execution_id = execution_id
        # Track chains: {tool_id: [previous_tool_id1, previous_tool_id2, ...]}
        self.chains: Dict[str, List[str]] = defaultdict(list)
        # Track call order
        self.call_order: List[str] = []

    def record_tool_call(
        self,
        tool_id: str,
        previous_tool_id: Optional[str] = None
    ) -> None:
        """
        Record a tool call in the chain

        Args:
            tool_id: Tool ID being called
            previous_tool_id: Previous tool ID in the chain (if any)
        """
        if previous_tool_id:
            self.chains[tool_id].append(previous_tool_id)
        self.call_order.append(tool_id)
        logger.debug(f"ToolCallChainTracker: Recorded {tool_id} (previous: {previous_tool_id})")

    def get_chain_length(self, tool_id: str) -> int:
        """
        Get the chain length for a tool (how many tools called before it)

        Args:
            tool_id: Tool ID

        Returns:
            Chain length (number of previous tools in chain)
        """
        return len(self.chains.get(tool_id, []))

    def get_longest_chain(self) -> int:
        """
        Get the longest chain length in this execution

        Returns:
            Longest chain length
        """
        if not self.chains:
            return 0
        return max(len(chain) for chain in self.chains.values())

    def reset(self) -> None:
        """Reset chain tracker (for new execution)"""
        self.chains.clear()
        self.call_order.clear()


# Global registry of chain trackers (keyed by execution_id)
_chain_trackers: Dict[str, ToolCallChainTracker] = {}


def get_chain_tracker(execution_id: str) -> ToolCallChainTracker:
    """
    Get or create chain tracker for an execution

    Args:
        execution_id: Execution ID

    Returns:
        ToolCallChainTracker instance
    """
    if execution_id not in _chain_trackers:
        _chain_trackers[execution_id] = ToolCallChainTracker(execution_id)
    return _chain_trackers[execution_id]


def reset_chain_tracker(execution_id: str) -> None:
    """
    Reset chain tracker for an execution

    Args:
        execution_id: Execution ID
    """
    if execution_id in _chain_trackers:
        _chain_trackers[execution_id].reset()
        del _chain_trackers[execution_id]

