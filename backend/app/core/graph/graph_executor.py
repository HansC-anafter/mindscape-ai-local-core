"""
Graph Executor

Executes graph-based workflows with state management.
"""

import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from backend.app.core.ir.graph_ir import GraphIR, GraphNode, GraphEdge, NodeType, EdgeType, StateType
from backend.app.core.state.state_manager import StateManager, WriteRule
from backend.app.core.state.world_state import WorldState
from backend.app.core.state.plan_state import PlanState
from backend.app.core.state.decision_state import DecisionState

logger = logging.getLogger(__name__)


class GraphExecutionState:
    """Graph execution state"""

    def __init__(self, graph: GraphIR, execution_id: str):
        self.graph = graph
        self.execution_id = execution_id
        self.current_node_id: Optional[str] = None
        self.visited_nodes: set = set()
        self.execution_history: List[Dict[str, Any]] = []
        self.state_manager: Optional[StateManager] = None

    def mark_visited(self, node_id: str) -> None:
        """Mark node as visited"""
        self.visited_nodes.add(node_id)

    def is_visited(self, node_id: str) -> bool:
        """Check if node is visited"""
        return node_id in self.visited_nodes

    def add_history(self, entry: Dict[str, Any]) -> None:
        """Add execution history entry"""
        entry["timestamp"] = _utc_now().isoformat()
        self.execution_history.append(entry)


class GraphExecutor:
    """
    Graph executor

    Executes graph-based workflows with state management.
    """

    def __init__(self, state_manager: Optional[StateManager] = None):
        """
        Initialize GraphExecutor

        Args:
            state_manager: StateManager instance (will create if not provided)
        """
        self.state_manager = state_manager

    async def execute(
        self,
        graph: GraphIR,
        initial_context: Optional[Dict[str, Any]] = None,
        execution_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a graph

        Args:
            graph: GraphIR instance to execute
            initial_context: Initial execution context
            execution_id: Execution ID (will generate if not provided)

        Returns:
            Execution result dictionary
        """
        if execution_id is None:
            execution_id = str(uuid.uuid4())

        execution_state = GraphExecutionState(graph, execution_id)

        # Initialize state manager if needed
        if execution_state.state_manager is None:
            # StateManager needs store, but we'll handle this in integration
            pass

        try:
            # Find start node
            start_node = self._find_start_node(graph)
            if not start_node:
                raise ValueError("No start node found in graph")

            # Execute graph starting from start node
            result = await self._execute_node(
                graph=graph,
                node=start_node,
                execution_state=execution_state,
                context=initial_context or {}
            )

            logger.info(f"GraphExecutor: Completed execution {execution_id} for graph '{graph.graph_id}'")
            return {
                "execution_id": execution_id,
                "status": "completed",
                "result": result,
                "history": execution_state.execution_history,
            }

        except Exception as e:
            logger.error(f"GraphExecutor: Execution {execution_id} failed: {e}", exc_info=True)
            return {
                "execution_id": execution_id,
                "status": "failed",
                "error": str(e),
                "history": execution_state.execution_history,
            }

    def _find_start_node(self, graph: GraphIR) -> Optional[GraphNode]:
        """Find start node in graph"""
        for node in graph.nodes:
            if node.node_type == NodeType.START:
                return node
        return None

    async def _execute_node(
        self,
        graph: GraphIR,
        node: GraphNode,
        execution_state: GraphExecutionState,
        context: Dict[str, Any]
    ) -> Any:
        """
        Execute a single node

        Args:
            graph: GraphIR instance
            node: GraphNode to execute
            execution_state: Current execution state
            context: Execution context

        Returns:
            Node execution result
        """
        # Mark node as visited
        execution_state.mark_visited(node.node_id)
        execution_state.current_node_id = node.node_id

        # Log execution
        execution_state.add_history({
            "node_id": node.node_id,
            "node_type": node.node_type.value,
            "action": "execute",
        })

        # Execute based on node type
        if node.node_type == NodeType.START:
            result = await self._execute_start_node(node, context)
        elif node.node_type == NodeType.END:
            result = await self._execute_end_node(node, context)
        elif node.node_type == NodeType.TASK:
            result = await self._execute_task_node(node, context)
        elif node.node_type == NodeType.DECISION:
            result = await self._execute_decision_node(node, context)
        elif node.node_type == NodeType.TOOL_CALL:
            result = await self._execute_tool_call_node(node, context)
        elif node.node_type == NodeType.PLAYBOOK:
            result = await self._execute_playbook_node(node, context)
        else:
            logger.warning(f"GraphExecutor: Unknown node type {node.node_type}, skipping")
            result = None

        # Update state
        await self._update_node_state(graph, node, result, execution_state)

        # Get next nodes
        next_edges = graph.get_edges_from(node.node_id)
        if not next_edges:
            return result

        # Execute next nodes
        next_results = []
        for edge in next_edges:
            if await self._should_traverse_edge(edge, context, result):
                next_node = graph.get_node(edge.to_node_id)
                if next_node:
                    next_result = await self._execute_node(
                        graph=graph,
                        node=next_node,
                        execution_state=execution_state,
                        context=context
                    )
                    next_results.append(next_result)

        return result if not next_results else next_results

    async def _execute_start_node(
        self,
        node: GraphNode,
        context: Dict[str, Any]
    ) -> Any:
        """Execute start node"""
        logger.debug(f"GraphExecutor: Executing start node {node.node_id}")
        return {"status": "started"}

    async def _execute_end_node(
        self,
        node: GraphNode,
        context: Dict[str, Any]
    ) -> Any:
        """Execute end node"""
        logger.debug(f"GraphExecutor: Executing end node {node.node_id}")
        return {"status": "completed"}

    async def _execute_task_node(
        self,
        node: GraphNode,
        context: Dict[str, Any]
    ) -> Any:
        """Execute task node"""
        logger.debug(f"GraphExecutor: Executing task node {node.node_id}")
        # Placeholder: actual task execution would be implemented here
        return {"status": "task_executed", "node_id": node.node_id}

    async def _execute_decision_node(
        self,
        node: GraphNode,
        context: Dict[str, Any]
    ) -> Any:
        """Execute decision node"""
        logger.debug(f"GraphExecutor: Executing decision node {node.node_id}")
        # Placeholder: actual decision logic would be implemented here
        # For now, evaluate condition from context
        condition = node.condition or "true"
        result = self._evaluate_condition(condition, context)
        return {"status": "decision_made", "result": result, "node_id": node.node_id}

    async def _execute_tool_call_node(
        self,
        node: GraphNode,
        context: Dict[str, Any]
    ) -> Any:
        """Execute tool call node"""
        logger.debug(f"GraphExecutor: Executing tool call node {node.node_id}")
        # Placeholder: actual tool execution would be implemented here
        # This would integrate with PlaybookToolExecutor
        tool_slot = node.task_slot
        if tool_slot:
            # TODO: Integrate with actual tool execution
            return {"status": "tool_executed", "tool_slot": tool_slot, "node_id": node.node_id}
        return {"status": "tool_call_skipped", "node_id": node.node_id}

    async def _execute_playbook_node(
        self,
        node: GraphNode,
        context: Dict[str, Any]
    ) -> Any:
        """Execute playbook node"""
        logger.debug(f"GraphExecutor: Executing playbook node {node.node_id}")
        # Placeholder: actual playbook execution would be implemented here
        # This would integrate with PlaybookService
        playbook_code = node.playbook_code
        if playbook_code:
            # TODO: Integrate with actual playbook execution
            return {"status": "playbook_executed", "playbook_code": playbook_code, "node_id": node.node_id}
        return {"status": "playbook_skipped", "node_id": node.node_id}

    async def _should_traverse_edge(
        self,
        edge: GraphEdge,
        context: Dict[str, Any],
        previous_result: Any
    ) -> bool:
        """Determine if edge should be traversed"""
        if edge.edge_type == EdgeType.SEQUENTIAL:
            return True
        elif edge.edge_type == EdgeType.CONDITIONAL:
            if edge.condition:
                return self._evaluate_condition(edge.condition, context)
            return True
        elif edge.edge_type == EdgeType.ERROR:
            # Only traverse on error
            return isinstance(previous_result, Exception) or (
                isinstance(previous_result, dict) and previous_result.get("status") == "error"
            )
        else:
            return True

    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Evaluate condition expression"""
        # Simple condition evaluation (can be extended with full expression parser)
        try:
            # For now, just check if condition key exists in context
            if condition in context:
                return bool(context[condition])
            # Try to evaluate as Python expression (with safety checks)
            # In production, use a proper expression evaluator
            return eval(condition, {"__builtins__": {}}, context)
        except Exception as e:
            logger.warning(f"GraphExecutor: Failed to evaluate condition '{condition}': {e}")
            return False

    async def _update_node_state(
        self,
        graph: GraphIR,
        node: GraphNode,
        result: Any,
        execution_state: GraphExecutionState
    ) -> None:
        """Update state for node execution"""
        # Get states associated with this node
        node_states = graph.get_states_by_node(node.node_id)
        for state in node_states:
            # Update state based on result
            if state.state_type == StateType.WORLD:
                # Update world state (tool results)
                if execution_state.state_manager:
                    # TODO: Integrate with StateManager
                    pass
            elif state.state_type == StateType.PLAN:
                # Update plan state
                if execution_state.state_manager:
                    # TODO: Integrate with StateManager
                    pass
            elif state.state_type == StateType.DECISION:
                # Update decision state
                if execution_state.state_manager:
                    # TODO: Integrate with StateManager
                    pass










