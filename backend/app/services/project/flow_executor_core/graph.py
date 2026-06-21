"""Graph parsing and ordering helpers for project flow execution."""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict, List, Set

from backend.app.models.playbook_flow import FlowEdge, FlowNode

logger = logging.getLogger(__name__)


class FlowGraphMixin:
    """Graph helper methods for FlowExecutor."""

    def _parse_nodes(self, flow_definition: Dict[str, Any]) -> Dict[str, FlowNode]:
        """Parse FlowNode objects from a flow definition."""
        nodes = {}
        nodes_data = flow_definition.get("nodes", [])

        for node_data in nodes_data:
            node = FlowNode(**node_data)
            nodes[node.id] = node

        return nodes

    def _build_nodes_from_playbook_sequence(
        self,
        playbook_sequence: List[str],
    ) -> Dict[str, FlowNode]:
        """
        Build FlowNode objects from a playbook sequence.

        Args:
            playbook_sequence: Playbook codes in execution order

        Returns:
            Dictionary of node ID to FlowNode
        """
        nodes = {}
        for idx, playbook_code in enumerate(playbook_sequence):
            if not playbook_code:
                continue
            node_id = f"node_{idx + 1}"
            node = FlowNode(
                id=node_id,
                name=f"Node {idx + 1}: {playbook_code}",
                playbook_code=playbook_code,
                inputs={},
                node_type="playbook",
            )
            nodes[node_id] = node
            logger.info(f"Built node {node_id} from playbook_sequence: {playbook_code}")
        return nodes

    def _parse_edges(self, flow_definition: Dict[str, Any]) -> List[FlowEdge]:
        """Parse FlowEdge objects from a flow definition."""
        edges_data = flow_definition.get("edges", [])
        return [FlowEdge(**edge_data) for edge_data in edges_data]

    def _get_execution_order(
        self,
        nodes: Dict[str, FlowNode],
        edges: List[FlowEdge],
        completed_nodes: Set[str],
    ) -> List[str]:
        """
        Get topological order of nodes for execution.

        Args:
            nodes: Dictionary of node ID to FlowNode
            edges: Flow dependencies
            completed_nodes: Already completed node IDs

        Returns:
            Ordered list of node IDs to execute
        """
        graph = {node_id: [] for node_id in nodes.keys()}
        in_degree = {node_id: 0 for node_id in nodes.keys()}

        for edge in edges:
            if edge.from_node in nodes and edge.to_node in nodes:
                graph[edge.from_node].append(edge.to_node)
                in_degree[edge.to_node] += 1

        queue = deque(
            [
                node_id
                for node_id in nodes.keys()
                if in_degree[node_id] == 0 and node_id not in completed_nodes
            ]
        )

        execution_order = []

        while queue:
            node_id = queue.popleft()
            execution_order.append(node_id)

            for neighbor in graph[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0 and neighbor not in completed_nodes:
                    queue.append(neighbor)

        return execution_order

    def _get_completed_nodes_before(
        self,
        nodes: Dict[str, FlowNode],
        edges: List[FlowEdge],
        resume_from: str,
    ) -> Set[str]:
        """
        Get nodes that should be completed before a resume point.

        Args:
            nodes: Dictionary of node ID to FlowNode
            edges: Flow dependencies
            resume_from: Node ID to resume from

        Returns:
            Set of node IDs to treat as completed
        """
        if resume_from not in nodes:
            return set()

        predecessors = set()
        graph = {node_id: [] for node_id in nodes.keys()}

        for edge in edges:
            if edge.from_node in nodes and edge.to_node in nodes:
                graph[edge.from_node].append(edge.to_node)

        def collect_predecessors(node_id: str, visited: Set[str]):
            if node_id in visited:
                return
            visited.add(node_id)
            for from_node, to_nodes in graph.items():
                if node_id in to_nodes and from_node != resume_from:
                    predecessors.add(from_node)
                    collect_predecessors(from_node, visited)

        visited = set()
        collect_predecessors(resume_from, visited)

        return predecessors
