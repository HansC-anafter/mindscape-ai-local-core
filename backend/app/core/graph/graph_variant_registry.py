"""
Graph Variant Registry

Manages graph variants (fast path vs safe path) for workflow execution.
"""

import logging
from typing import Dict, List, Optional, Any
from enum import Enum

from backend.app.core.ir.graph_ir import GraphIR, GraphNode, GraphEdge, NodeType, EdgeType

logger = logging.getLogger(__name__)


class VariantType(str, Enum):
    """Graph variant type"""
    FAST_PATH = "fast_path"  # Optimized for speed
    SAFE_PATH = "safe_path"  # Optimized for safety/reliability
    BALANCED = "balanced"  # Balanced between speed and safety
    CUSTOM = "custom"  # Custom variant


class GraphVariantRegistry:
    """
    Registry for graph variants

    Manages multiple variants of the same graph (e.g., fast_path, safe_path)
    for different execution strategies.
    """

    def __init__(self):
        """Initialize GraphVariantRegistry"""
        self._variants: Dict[str, Dict[str, GraphIR]] = {}  # {graph_id: {variant_name: GraphIR}}
        self._default_variants: Dict[str, str] = {}  # {graph_id: default_variant_name}

    def register_variant(
        self,
        graph: GraphIR,
        variant_name: Optional[str] = None
    ) -> None:
        """
        Register a graph variant

        Args:
            graph: GraphIR instance
            variant_name: Variant name (defaults to graph.variant_name or "default")
        """
        graph_id = graph.graph_id
        variant_name = variant_name or graph.variant_name or "default"

        if graph_id not in self._variants:
            self._variants[graph_id] = {}

        self._variants[graph_id][variant_name] = graph

        # Set as default if it's the first variant
        if graph_id not in self._default_variants:
            self._default_variants[graph_id] = variant_name

        logger.info(f"GraphVariantRegistry: Registered variant '{variant_name}' for graph '{graph_id}'")

    def get_variant(
        self,
        graph_id: str,
        variant_name: Optional[str] = None
    ) -> Optional[GraphIR]:
        """
        Get a graph variant

        Args:
            graph_id: Graph ID
            variant_name: Variant name (defaults to default variant)

        Returns:
            GraphIR instance or None if not found
        """
        if graph_id not in self._variants:
            return None

        if variant_name is None:
            variant_name = self._default_variants.get(graph_id, "default")

        return self._variants[graph_id].get(variant_name)

    def list_variants(self, graph_id: str) -> List[str]:
        """
        List all variants for a graph

        Args:
            graph_id: Graph ID

        Returns:
            List of variant names
        """
        if graph_id not in self._variants:
            return []
        return list(self._variants[graph_id].keys())

    def set_default_variant(
        self,
        graph_id: str,
        variant_name: str
    ) -> bool:
        """
        Set default variant for a graph

        Args:
            graph_id: Graph ID
            variant_name: Variant name

        Returns:
            True if successful, False if variant not found
        """
        if graph_id not in self._variants:
            return False
        if variant_name not in self._variants[graph_id]:
            return False

        self._default_variants[graph_id] = variant_name
        logger.info(f"GraphVariantRegistry: Set default variant '{variant_name}' for graph '{graph_id}'")
        return True

    def create_fast_path_variant(
        self,
        base_graph: GraphIR
    ) -> GraphIR:
        """
        Create a fast path variant from base graph

        Fast path optimizations:
        - Skip optional validation steps
        - Use faster models for non-critical stages
        - Reduce parallel execution overhead
        - Skip intermediate confirmations

        Args:
            base_graph: Base GraphIR instance

        Returns:
            Fast path GraphIR variant
        """
        fast_path = GraphIR(
            graph_id=base_graph.graph_id,
            graph_name=f"{base_graph.graph_name} (Fast Path)",
            description=f"Fast path variant of {base_graph.graph_name}",
            nodes=base_graph.nodes.copy(),
            edges=base_graph.edges.copy(),
            states=base_graph.states.copy(),
            variant_name=VariantType.FAST_PATH.value,
            tags=base_graph.tags + ["fast", "optimized"],
            metadata={
                **base_graph.metadata,
                "optimization": "speed",
                "base_graph_id": base_graph.graph_id,
            }
        )

        # Optimize edges: remove optional validation edges
        fast_path.edges = [
            edge for edge in fast_path.edges
            if not edge.metadata.get("optional_validation", False)
        ]

        # Optimize nodes: mark for fast model selection
        for node in fast_path.nodes:
            if node.node_type == NodeType.TOOL_CALL:
                node.metadata["prefer_fast_model"] = True

        logger.info(f"GraphVariantRegistry: Created fast path variant for graph '{base_graph.graph_id}'")
        return fast_path

    def create_safe_path_variant(
        self,
        base_graph: GraphIR
    ) -> GraphIR:
        """
        Create a safe path variant from base graph

        Safe path optimizations:
        - Add additional validation steps
        - Use stronger models for critical stages
        - Add intermediate confirmations
        - Enable rollback points

        Args:
            base_graph: Base GraphIR instance

        Returns:
            Safe path GraphIR variant
        """
        safe_path = GraphIR(
            graph_id=base_graph.graph_id,
            graph_name=f"{base_graph.graph_name} (Safe Path)",
            description=f"Safe path variant of {base_graph.graph_name}",
            nodes=base_graph.nodes.copy(),
            edges=base_graph.edges.copy(),
            states=base_graph.states.copy(),
            variant_name=VariantType.SAFE_PATH.value,
            tags=base_graph.tags + ["safe", "reliable"],
            metadata={
                **base_graph.metadata,
                "optimization": "safety",
                "base_graph_id": base_graph.graph_id,
            }
        )

        # Add validation nodes for critical tool calls
        validation_nodes = []
        for node in safe_path.nodes:
            if node.node_type == NodeType.TOOL_CALL:
                risk_level = node.metadata.get("risk_level", "low")
                if risk_level in ["high", "critical"]:
                    # Add validation node before critical tool calls
                    validation_node = GraphNode(
                        node_id=f"{node.node_id}_validation",
                        node_type=NodeType.DECISION,
                        label=f"Validate {node.label}",
                        description=f"Validation step for {node.label}",
                        condition=f"validate_{node.node_id}",
                        metadata={
                            "validation_for": node.node_id,
                            "risk_level": risk_level,
                        }
                    )
                    validation_nodes.append(validation_node)

        # Insert validation nodes and edges
        for validation_node in validation_nodes:
            safe_path.nodes.append(validation_node)
            target_node_id = validation_node.metadata["validation_for"]
            target_node = safe_path.get_node(target_node_id)
            if target_node:
                # Add edge from validation to target
                validation_edge = GraphEdge(
                    edge_id=f"{validation_node.node_id}_to_{target_node_id}",
                    from_node_id=validation_node.node_id,
                    to_node_id=target_node_id,
                    edge_type=EdgeType.CONDITIONAL,
                    condition="validation_passed",
                    metadata={"validation": True}
                )
                safe_path.edges.append(validation_edge)

        # Mark nodes for strong model selection
        for node in safe_path.nodes:
            if node.node_type == NodeType.TOOL_CALL:
                node.metadata["prefer_strong_model"] = True

        logger.info(f"GraphVariantRegistry: Created safe path variant for graph '{base_graph.graph_id}'")
        return safe_path

    def create_balanced_variant(
        self,
        base_graph: GraphIR
    ) -> GraphIR:
        """
        Create a balanced variant from base graph

        Balanced variant:
        - Mix of fast and safe optimizations
        - Use fast models for non-critical stages
        - Use strong models for critical stages
        - Moderate validation

        Args:
            base_graph: Base GraphIR instance

        Returns:
            Balanced GraphIR variant
        """
        balanced = GraphIR(
            graph_id=base_graph.graph_id,
            graph_name=f"{base_graph.graph_name} (Balanced)",
            description=f"Balanced variant of {base_graph.graph_name}",
            nodes=base_graph.nodes.copy(),
            edges=base_graph.edges.copy(),
            states=base_graph.states.copy(),
            variant_name=VariantType.BALANCED.value,
            tags=base_graph.tags + ["balanced"],
            metadata={
                **base_graph.metadata,
                "optimization": "balanced",
                "base_graph_id": base_graph.graph_id,
            }
        )

        # Mark nodes based on risk level
        for node in balanced.nodes:
            if node.node_type == NodeType.TOOL_CALL:
                risk_level = node.metadata.get("risk_level", "low")
                if risk_level in ["high", "critical"]:
                    node.metadata["prefer_strong_model"] = True
                else:
                    node.metadata["prefer_fast_model"] = True

        logger.info(f"GraphVariantRegistry: Created balanced variant for graph '{base_graph.graph_id}'")
        return balanced

