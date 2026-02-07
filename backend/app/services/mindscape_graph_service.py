"""
Mindscape Graph Service - Core service for Mind Space visualization

Implements the "derived graph + overlay" architecture:
- 80% of graph derived from existing data (TimelineItems, ExecutionSessions, Artifacts)
- 20% stored as overlay (positions, renames, merge redirects, manual nodes/edges)

This is the backend for the "executable mind map" visualization.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ==================== Node ID Generation ====================


class NodeIdPrefix(str, Enum):
    """Stable node ID prefixes for different node types"""

    INTENT = "intent"
    EXECUTION = "execution"
    PLAYBOOK = "playbook"
    STEP = "step"
    ARTIFACT = "artifact"
    MANUAL = "manual"


def generate_node_id(prefix: NodeIdPrefix, *parts: str) -> str:
    """
    Generate stable node ID from prefix and parts.

    Examples:
        - intent:ti_abc123
        - execution:exec_xyz789
        - playbook:ig_analyze@v1.2.3
        - step:exec_xyz789:s1
        - artifact:art_def456
        - manual:uuid
    """
    return f"{prefix.value}:{':'.join(parts)}"


def generate_edge_id(from_id: str, to_id: str, edge_type: str) -> str:
    """
    Generate edge ID using hash to avoid overly long IDs.

    Format: edge:<sha1(from|to|type).slice(0,12)>
    """
    content = f"{from_id}|{to_id}|{edge_type}"
    hash_value = hashlib.sha1(content.encode()).hexdigest()[:12]
    return f"edge:{hash_value}"


# ==================== Data Models ====================


class EdgeType(str, Enum):
    """Edge types with confidence levels defined in derivation rules"""

    TEMPORAL = "temporal"  # 0.9 confidence
    SPAWNS = "spawns"  # 1.0 confidence
    PRODUCES = "produces"  # 1.0 confidence
    DEPENDENCY = "dependency"  # 1.0 confidence
    CAUSAL = "causal"  # 0.7 confidence
    REFERS_TO = "refers_to"  # 0.5-0.8 confidence


class EdgeOrigin(str, Enum):
    """Origin of edge - derived by system or created by user"""

    DERIVED = "derived"
    USER = "user"


class NodeStatus(str, Enum):
    """Node status for suggested vs confirmed nodes"""

    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass
class MindscapeNode:
    """Base node in the mindscape graph"""

    id: str
    type: str
    label: str
    status: NodeStatus = NodeStatus.SUGGESTED
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MindscapeEdge:
    """Edge in the mindscape graph"""

    id: str
    from_id: str
    to_id: str
    type: EdgeType
    origin: EdgeOrigin = EdgeOrigin.DERIVED
    confidence: float = 1.0
    status: NodeStatus = NodeStatus.SUGGESTED
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OverlayNode:
    """Manually created node in overlay"""

    id: str
    type: str  # 'intent' | 'note' | 'milestone'
    label: str
    position: Dict[str, float]  # {x, y}
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphOverlay:
    """
    Overlay layer storing user modifications.

    Only stores the 20% that can't be derived:
    - Node positions (user's mental layout)
    - Collapsed states
    - Renames and merge redirects
    - Manual nodes and edges
    - Status overrides
    """

    # Node positions (user's layout is product asset)
    node_positions: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Collapsed/expanded state for progressive disclosure
    collapsed_state: Dict[str, bool] = field(default_factory=dict)

    # Viewport state (return to last working state)
    viewport: Optional[Dict[str, float]] = None  # {x, y, zoom}

    # Node renames
    renames: Dict[str, str] = field(default_factory=dict)

    # Merge redirects (alias/redirect, not delete)
    merge_redirects: Dict[str, str] = field(default_factory=dict)

    # Manually created nodes
    manual_nodes: List[OverlayNode] = field(default_factory=list)

    # Manually created edges
    manual_edges: List[MindscapeEdge] = field(default_factory=list)

    # Status overrides (split for node/edge)
    node_status_overrides: Dict[str, str] = field(default_factory=dict)
    edge_status_overrides: Dict[str, str] = field(default_factory=dict)

    # Version for cache invalidation
    version: int = 0


@dataclass
class MindscapeGraph:
    """Complete mindscape graph combining derived + overlay"""

    nodes: List[MindscapeNode] = field(default_factory=list)
    edges: List[MindscapeEdge] = field(default_factory=list)
    overlay: GraphOverlay = field(default_factory=GraphOverlay)

    # Cache metadata
    scope_type: str = "workspace"  # workspace | workspace_group
    scope_id: str = ""
    last_event_seq: int = 0
    derived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ==================== Derivation Rules ====================


@dataclass
class DerivationRule:
    """Rule for deriving edges from existing data"""

    edge_type: EdgeType
    source: str
    confidence: float
    description: str


# Core derivation rules (護城河)
DERIVATION_RULES: List[DerivationRule] = [
    DerivationRule(
        edge_type=EdgeType.TEMPORAL,
        source="timeline_items",
        confidence=0.9,
        description="Connect timeline items by created_at order",
    ),
    DerivationRule(
        edge_type=EdgeType.SPAWNS,
        source="intent_to_execution",
        confidence=1.0,
        description="Intent → Execution when linkedExecutionId exists",
    ),
    DerivationRule(
        edge_type=EdgeType.PRODUCES,
        source="artifact_registry",
        confidence=1.0,
        description="Execution/Step → Artifact via source_ref",
    ),
    DerivationRule(
        edge_type=EdgeType.DEPENDENCY,
        source="playbook_steps",
        confidence=1.0,
        description="Step A → Step B via PlaybookJson.steps dependencies",
    ),
    DerivationRule(
        edge_type=EdgeType.CAUSAL,
        source="conversation_window",
        confidence=0.7,
        description="Decision/Constraint → Intent in same conversation window",
    ),
    DerivationRule(
        edge_type=EdgeType.REFERS_TO,
        source="nlp_extraction",
        confidence=0.6,
        description="References to other Intent/Artifact via NLP",
    ),
]


def _normalize_datetime(dt: Optional[datetime]) -> datetime:
    """
    Normalize datetime for comparison.
    Converts offset-naive to UTC and ensures all datetimes are comparable.
    """
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ==================== Graph Service ====================


class MindscapeGraphService:
    """
    Core service for mindscape graph operations.

    Implements:
    - derive(): Generate graph from existing data sources
    - apply_overlay(): Merge overlay modifications
    - canonicalize(): Apply merge redirects to all references
    """

    def __init__(self, db_path: str):
        """
        Initialize graph service.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._overlay_cache: Dict[str, GraphOverlay] = {}
        logger.info(f"MindscapeGraphService initialized with db_path: {db_path}")

    async def get_graph(
        self,
        workspace_id: Optional[str] = None,
        workspace_group_id: Optional[str] = None,
    ) -> MindscapeGraph:
        """
        Get complete mindscape graph for workspace or group.

        Args:
            workspace_id: Single workspace ID
            workspace_group_id: Workspace group ID for aggregated view

        Returns:
            Complete MindscapeGraph with derived nodes/edges + overlay
        """
        if not workspace_id and not workspace_group_id:
            raise ValueError("Either workspace_id or workspace_group_id required")

        scope_type = "workspace" if workspace_id else "workspace_group"
        scope_id = workspace_id or workspace_group_id

        # Step 1: Derive base graph from existing data
        graph = await self._derive_graph(scope_type, scope_id)

        # Step 2: Load and apply overlay
        overlay = await self._load_overlay(scope_type, scope_id)
        graph = self._apply_overlay(graph, overlay)

        # Step 3: Canonicalize (apply merge redirects)
        graph = self._canonicalize(graph)

        return graph

    async def _derive_graph(self, scope_type: str, scope_id: str) -> MindscapeGraph:
        """
        Derive graph from existing data sources.

        This is the core derivation logic that generates 80% of the graph
        from TimelineItems, ExecutionSessions, and Artifacts.
        """
        graph = MindscapeGraph(scope_type=scope_type, scope_id=scope_id)

        # Import stores lazily to avoid circular imports
        from app.services.stores.timeline_items_store import TimelineItemsStore
        from app.services.stores.tasks_store import TasksStore

        timeline_store = TimelineItemsStore(self.db_path)
        tasks_store = TasksStore(self.db_path)

        # Get workspace IDs to process
        workspace_ids = await self._get_workspace_ids(scope_type, scope_id)

        for ws_id in workspace_ids:
            # Derive from timeline items (Intent nodes)
            await self._derive_from_timeline(graph, ws_id, timeline_store, tasks_store)

            # Derive from tasks/executions (Execution nodes)
            await self._derive_from_executions(graph, ws_id, tasks_store)

            # Derive from artifacts (Artifact nodes)
            await self._derive_from_artifacts(graph, ws_id)

        # Derive edges based on rules
        self._derive_edges(graph)

        graph.derived_at = datetime.now(timezone.utc)
        return graph

    async def _get_workspace_ids(self, scope_type: str, scope_id: str) -> List[str]:
        """Get workspace IDs for the given scope"""
        if scope_type == "workspace":
            return [scope_id]
        else:
            # For workspace groups, get all member workspaces
            from app.services.stores.workspaces_store import WorkspacesStore

            store = WorkspacesStore(self.db_path)
            group = store.get_workspace_group(scope_id)
            return group.workspace_ids if group else []

    async def _derive_from_timeline(
        self, graph: MindscapeGraph, workspace_id: str, timeline_store, tasks_store
    ) -> None:
        """Derive Intent nodes from timeline items with playbook associations"""
        items = timeline_store.list_timeline_items_by_workspace(
            workspace_id=workspace_id, limit=500
        )

        # Build task lookup cache for efficiency
        task_cache: Dict[str, Any] = {}

        for item in items:
            # Get playbook codes from associated task
            linked_playbook_codes: List[str] = []

            if item.task_id:
                # Check cache first
                if item.task_id not in task_cache:
                    task = tasks_store.get_task(item.task_id)
                    task_cache[item.task_id] = task
                else:
                    task = task_cache[item.task_id]

                if task:
                    # Extract playbook_code from execution_context
                    if task.execution_context:
                        playbook_code = task.execution_context.get("playbook_code")
                        if playbook_code:
                            linked_playbook_codes.append(playbook_code)

                    # Also check params for playbook_code
                    if task.params and not linked_playbook_codes:
                        playbook_code = task.params.get("playbook_code")
                        if playbook_code:
                            linked_playbook_codes.append(playbook_code)

            # Also check timeline item data for intent analysis
            if item.data:
                intent_analysis = item.data.get("intent_analysis", {})
                if isinstance(intent_analysis, dict):
                    playbook_code = intent_analysis.get("playbook_code")
                    if playbook_code and playbook_code not in linked_playbook_codes:
                        linked_playbook_codes.append(playbook_code)

            # Get project_id from task if available
            project_id = None
            if item.task_id and task_cache.get(item.task_id):
                cached_task = task_cache[item.task_id]
                project_id = getattr(cached_task, "project_id", None)

            # Get thread_id from timeline item data (for conversation tracking)
            thread_id = None
            if item.data and isinstance(item.data, dict):
                thread_id = item.data.get("thread_id")

            node_id = generate_node_id(NodeIdPrefix.INTENT, item.id)
            node = MindscapeNode(
                id=node_id,
                type="intent",
                label=item.title or item.summary or "Untitled",
                status=NodeStatus.SUGGESTED,
                metadata={
                    "timeline_item_id": item.id,
                    "timeline_type": item.type.value if item.type else None,
                    "message_id": item.message_id,
                    "task_id": item.task_id,
                    "project_id": project_id,
                    "thread_id": thread_id,
                    "linked_playbook_codes": linked_playbook_codes,
                },
                created_at=item.created_at,
            )
            graph.nodes.append(node)

    async def _derive_from_executions(
        self, graph: MindscapeGraph, workspace_id: str, tasks_store
    ) -> None:
        """Derive Execution nodes from tasks with execution summary"""
        tasks = tasks_store.list_tasks_by_workspace(
            workspace_id=workspace_id, limit=500
        )

        for task in tasks:
            if not task.execution_id:
                continue

            node_id = generate_node_id(NodeIdPrefix.EXECUTION, task.execution_id)

            # Calculate run number (derived, not stored)
            # TODO: Implement proper run number calculation
            run_number = 1

            # Extract execution summary from result
            result_summary = None
            artifact_count = 0
            if task.result:
                # Try to get summary from result
                if isinstance(task.result, dict):
                    result_summary = task.result.get("summary") or task.result.get(
                        "message"
                    )
                    # Count artifacts if present
                    artifacts = task.result.get("artifacts", [])
                    artifact_count = (
                        len(artifacts) if isinstance(artifacts, list) else 0
                    )

            # Get playbook code from execution context
            playbook_code = None
            if task.execution_context:
                playbook_code = task.execution_context.get("playbook_code")
            if not playbook_code and task.params:
                playbook_code = task.params.get("playbook_code")

            node = MindscapeNode(
                id=node_id,
                type="execution",
                label=(
                    f"{task.pack_id}:{task.task_type}"
                    if task.pack_id
                    else task.task_type
                ),
                status=(
                    NodeStatus.ACCEPTED
                    if task.status.value == "succeeded"
                    else NodeStatus.SUGGESTED
                ),
                metadata={
                    "task_id": task.id,
                    "execution_id": task.execution_id,
                    "project_id": getattr(task, "project_id", None),
                    "pack_id": task.pack_id,
                    "task_type": task.task_type,
                    "status": task.status.value,
                    "run_number": run_number,
                    "playbook_code": playbook_code,
                    "result_summary": result_summary,
                    "artifact_count": artifact_count,
                    "completed_at": (
                        task.completed_at.isoformat() if task.completed_at else None
                    ),
                    "error": task.error,
                },
                created_at=task.created_at,
            )
            graph.nodes.append(node)

    async def _derive_from_artifacts(
        self, graph: MindscapeGraph, workspace_id: str
    ) -> None:
        """Derive Artifact nodes from artifact registry"""
        # TODO: Implement artifact derivation
        # This requires integrating with ArtifactRegistry
        pass

    def _derive_edges(self, graph: MindscapeGraph) -> None:
        """Derive edges based on derivation rules"""
        nodes_by_id = {n.id: n for n in graph.nodes}

        # Sort nodes by created_at for temporal edges
        sorted_nodes = sorted(
            graph.nodes, key=lambda n: _normalize_datetime(n.created_at)
        )

        # Temporal edges (consecutive timeline items)
        for i in range(len(sorted_nodes) - 1):
            current = sorted_nodes[i]
            next_node = sorted_nodes[i + 1]

            # Only connect same-type nodes temporally
            if current.type == next_node.type == "intent":
                edge = MindscapeEdge(
                    id=generate_edge_id(
                        current.id, next_node.id, EdgeType.TEMPORAL.value
                    ),
                    from_id=current.id,
                    to_id=next_node.id,
                    type=EdgeType.TEMPORAL,
                    origin=EdgeOrigin.DERIVED,
                    confidence=0.9,
                )
                graph.edges.append(edge)

        # Spawns edges (Intent → Execution)
        for node in graph.nodes:
            if node.type == "intent" and node.metadata.get("task_id"):
                task_id = node.metadata["task_id"]
                # Find execution node for this task
                for exec_node in graph.nodes:
                    if (
                        exec_node.type == "execution"
                        and exec_node.metadata.get("task_id") == task_id
                    ):
                        edge = MindscapeEdge(
                            id=generate_edge_id(
                                node.id, exec_node.id, EdgeType.SPAWNS.value
                            ),
                            from_id=node.id,
                            to_id=exec_node.id,
                            type=EdgeType.SPAWNS,
                            origin=EdgeOrigin.DERIVED,
                            confidence=1.0,
                        )
                        graph.edges.append(edge)

    async def _load_overlay(self, scope_type: str, scope_id: str) -> GraphOverlay:
        """Load overlay from storage"""
        cache_key = f"{scope_type}:{scope_id}"

        if cache_key in self._overlay_cache:
            return self._overlay_cache[cache_key]

        # Load from database
        try:
            from .stores.mindscape_overlay_store import MindscapeOverlayStore

            store = MindscapeOverlayStore(self.db_path)
            overlay = store.get_overlay(scope_type, scope_id)
        except Exception as e:
            # Table might not exist yet, return empty overlay
            logger.warning(f"Failed to load overlay (table may not exist): {e}")
            overlay = None

        if overlay is None:
            overlay = GraphOverlay()

        self._overlay_cache[cache_key] = overlay
        return overlay

    def _apply_overlay(
        self, graph: MindscapeGraph, overlay: GraphOverlay
    ) -> MindscapeGraph:
        """Apply overlay modifications to derived graph"""
        graph.overlay = overlay

        # Add manual nodes
        for manual_node in overlay.manual_nodes:
            node = MindscapeNode(
                id=manual_node.id,
                type=manual_node.type,
                label=manual_node.label,
                status=NodeStatus.ACCEPTED,
                metadata=manual_node.metadata,
            )
            graph.nodes.append(node)

        # Add manual edges
        graph.edges.extend(overlay.manual_edges)

        # Apply status overrides
        for node in graph.nodes:
            if node.id in overlay.node_status_overrides:
                node.status = NodeStatus(overlay.node_status_overrides[node.id])

        for edge in graph.edges:
            if edge.id in overlay.edge_status_overrides:
                edge.status = NodeStatus(overlay.edge_status_overrides[edge.id])

        # Apply renames
        for node in graph.nodes:
            if node.id in overlay.renames:
                node.label = overlay.renames[node.id]

        return graph

    def _canonicalize(self, graph: MindscapeGraph) -> MindscapeGraph:
        """
        Apply merge redirects to all references.

        IMPORTANT: Must handle ALL of these:
        - nodes[].id
        - manual_edges[].from / manual_edges[].to
        - derived edges from/to
        - node_positions keys
        - collapsed_state keys
        - renames keys
        """
        redirects = graph.overlay.merge_redirects
        if not redirects:
            return graph

        def redirect(node_id: str) -> str:
            """Follow redirect chain to canonical ID"""
            visited: Set[str] = set()
            current = node_id
            while current in redirects and current not in visited:
                visited.add(current)
                current = redirects[current]
            return current

        # Canonicalize node IDs (but keep originals for reverse lookup)
        canonical_nodes: Dict[str, MindscapeNode] = {}
        for node in graph.nodes:
            canonical_id = redirect(node.id)
            if canonical_id not in canonical_nodes:
                node.id = canonical_id
                canonical_nodes[canonical_id] = node

        graph.nodes = list(canonical_nodes.values())

        # Canonicalize edge references
        for edge in graph.edges:
            edge.from_id = redirect(edge.from_id)
            edge.to_id = redirect(edge.to_id)
            # Regenerate edge ID after canonicalization
            edge.id = generate_edge_id(edge.from_id, edge.to_id, edge.type.value)

        # Canonicalize overlay keys
        graph.overlay.node_positions = {
            redirect(k): v for k, v in graph.overlay.node_positions.items()
        }
        graph.overlay.collapsed_state = {
            redirect(k): v for k, v in graph.overlay.collapsed_state.items()
        }
        graph.overlay.renames = {
            redirect(k): v for k, v in graph.overlay.renames.items()
        }

        return graph

    async def update_overlay(
        self, scope_type: str, scope_id: str, updates: Dict[str, Any]
    ) -> GraphOverlay:
        """
        Update overlay with new modifications.

        Args:
            scope_type: 'workspace' or 'workspace_group'
            scope_id: Workspace or group ID
            updates: Dict with overlay field updates

        Returns:
            Updated GraphOverlay
        """
        overlay = await self._load_overlay(scope_type, scope_id)

        # Apply updates
        if "node_positions" in updates:
            overlay.node_positions.update(updates["node_positions"])
        if "collapsed_state" in updates:
            overlay.collapsed_state.update(updates["collapsed_state"])
        if "viewport" in updates:
            overlay.viewport = updates["viewport"]
        if "renames" in updates:
            overlay.renames.update(updates["renames"])
        if "merge_redirects" in updates:
            overlay.merge_redirects.update(updates["merge_redirects"])
        if "node_status_overrides" in updates:
            overlay.node_status_overrides.update(updates["node_status_overrides"])
        if "edge_status_overrides" in updates:
            overlay.edge_status_overrides.update(updates["edge_status_overrides"])

        overlay.version += 1

        # Update cache
        cache_key = f"{scope_type}:{scope_id}"
        self._overlay_cache[cache_key] = overlay

        # Persist to database
        from .stores.mindscape_overlay_store import MindscapeOverlayStore

        store = MindscapeOverlayStore(self.db_path)
        store.save_overlay(scope_type, scope_id, overlay)

        return overlay

    async def accept_node(self, scope_type: str, scope_id: str, node_id: str) -> bool:
        """Accept a suggested node"""
        await self.update_overlay(
            scope_type,
            scope_id,
            {"node_status_overrides": {node_id: NodeStatus.ACCEPTED.value}},
        )
        return True

    async def reject_node(self, scope_type: str, scope_id: str, node_id: str) -> bool:
        """Reject a suggested node"""
        await self.update_overlay(
            scope_type,
            scope_id,
            {"node_status_overrides": {node_id: NodeStatus.REJECTED.value}},
        )
        return True

    async def merge_nodes(
        self, scope_type: str, scope_id: str, source_node_id: str, target_node_id: str
    ) -> bool:
        """
        Merge source node into target (alias/redirect).

        Does NOT delete source node - creates redirect.
        """
        await self.update_overlay(
            scope_type, scope_id, {"merge_redirects": {source_node_id: target_node_id}}
        )
        return True
