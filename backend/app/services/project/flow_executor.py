"""
Flow Executor Service

Executes PlaybookFlow sequences within a Project context.
Manages node dependencies, checkpoint/resume, and artifact preservation.
"""

import logging
import asyncio
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, List, Optional, Set, Any
from collections import deque

from backend.app.models.playbook_flow import PlaybookFlow, FlowNode, FlowEdge
from backend.app.services.project.project_manager import ProjectManager
from backend.app.services.project.artifact_registry_service import ArtifactRegistryService
from backend.app.services.playbook_runner import PlaybookRunner
from backend.app.services.playbook_checkpoint_manager import PlaybookCheckpointManager
from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class FlowExecutionError(Exception):
    """Flow execution error"""
    pass


class FlowExecutor:
    """
    Executes PlaybookFlow sequences

    Manages execution of multi-playbook flows with:
    - Dependency resolution and topological ordering
    - Checkpoint/resume support
    - Artifact preservation on retry
    - Error handling and retry logic
    """

    def __init__(
        self,
        store: MindscapeStore,
        project_manager: Optional[ProjectManager] = None,
        artifact_registry: Optional[ArtifactRegistryService] = None,
        playbook_runner: Optional[PlaybookRunner] = None
    ):
        """
        Initialize FlowExecutor

        Args:
            store: MindscapeStore instance
            project_manager: ProjectManager instance (created if None)
            artifact_registry: ArtifactRegistryService instance (created if None)
            playbook_runner: PlaybookRunner instance (created if None)
        """
        self.store = store
        self.project_manager = project_manager or ProjectManager(store)
        self.artifact_registry = artifact_registry or ArtifactRegistryService(store)
        self.playbook_runner = playbook_runner or PlaybookRunner()

        self.checkpoint_manager = PlaybookCheckpointManager(store.playbook_executions)
        self.flows_store = PlaybookFlowsStore(db_path=store.db_path)

    async def execute_flow(
        self,
        project_id: str,
        workspace_id: str,
        profile_id: Optional[str] = None,
        resume_from: Optional[str] = None,
        preserve_artifacts: bool = True,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Execute a PlaybookFlow for a Project

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
            profile_id: User profile ID (for playbook execution)
            resume_from: Node ID to resume from (for partial retry)
            preserve_artifacts: Whether to preserve existing artifacts on retry
            max_retries: Maximum retry attempts per node

        Returns:
            Execution result with node outcomes

        Raises:
            FlowExecutionError: If flow execution fails
        """
        project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
        if not project:
            raise FlowExecutionError(f"Project {project_id} not found")

        flow = self.flows_store.get_flow(project.flow_id)
        if not flow:
            raise FlowExecutionError(f"Flow {project.flow_id} not found")

        # Parse nodes from flow definition
        # If nodes are empty but playbook_sequence exists, build nodes from playbook_sequence
        nodes = self._parse_nodes(flow.flow_definition)
        if not nodes:
            # Try to build nodes from playbook_sequence if nodes are empty
            playbook_sequence = flow.flow_definition.get("playbook_sequence", [])
            if playbook_sequence:
                logger.info(f"Flow has no nodes but has playbook_sequence, building nodes from sequence: {playbook_sequence}")
                nodes = self._build_nodes_from_playbook_sequence(playbook_sequence)

        edges = self._parse_edges(flow.flow_definition)

        if resume_from:
            completed_nodes = self._get_completed_nodes_before(nodes, edges, resume_from)
            logger.info(f"Resuming flow from node {resume_from}, completed: {completed_nodes}")
        else:
            completed_nodes = set()

        execution_order = self._get_execution_order(nodes, edges, completed_nodes)
        execution_results = {}

        try:
            for node_id in execution_order:
                if node_id in completed_nodes:
                    logger.info(f"Skipping completed node: {node_id}")
                    continue

                node = nodes[node_id]
                try:
                    result = await self._execute_node_with_retry(
                        node=node,
                        project_id=project_id,
                        workspace_id=workspace_id,
                        profile_id=profile_id or "default_user",
                        preserve_artifacts=preserve_artifacts,
                        max_retries=max_retries
                    )
                    execution_results[node_id] = result
                    completed_nodes.add(node_id)

                    # Save checkpoint after successful node execution
                    await self._save_flow_checkpoint(
                        project_id=project_id,
                        workspace_id=workspace_id,
                        flow_id=flow.id,
                        current_node=node_id,
                        completed_nodes=completed_nodes,
                        execution_results=execution_results
                    )
                except Exception as e:
                    logger.error(f"Node {node_id} failed after retries: {e}")
                    execution_results[node_id] = {
                        "status": "failed",
                        "error": str(e)
                    }

                    # Save checkpoint on failure for recovery
                    await self._save_flow_checkpoint(
                        project_id=project_id,
                        workspace_id=workspace_id,
                        flow_id=flow.id,
                        current_node=node_id,
                        completed_nodes=completed_nodes,
                        execution_results=execution_results,
                        failed_node=node_id,
                        failure_error=str(e)
                    )
                    raise FlowExecutionError(f"Flow execution failed at node {node_id}: {e}")

            # Clear checkpoint on successful completion
            await self._clear_flow_checkpoint(project_id, workspace_id)

            return {
                "project_id": project_id,
                "flow_id": flow.id,
                "completed_nodes": list(completed_nodes),
                "execution_results": execution_results,
                "status": "completed"
            }

        except FlowExecutionError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during flow execution: {e}")
            # Save checkpoint on unexpected error
            await self._save_flow_checkpoint(
                project_id=project_id,
                workspace_id=workspace_id,
                flow_id=flow.id,
                current_node=None,
                completed_nodes=completed_nodes,
                execution_results=execution_results,
                failure_error=str(e)
            )
            raise

    async def _execute_node_with_retry(
        self,
        node: FlowNode,
        project_id: str,
        workspace_id: str,
        profile_id: str,
        preserve_artifacts: bool,
        max_retries: int
    ) -> Dict[str, Any]:
        """
        Execute a flow node with retry logic

        Args:
            node: FlowNode to execute
            project_id: Project ID
            workspace_id: Workspace ID
            profile_id: User profile ID
            preserve_artifacts: Whether to preserve existing artifacts
            max_retries: Maximum retry attempts

        Returns:
            Node execution result

        Raises:
            Exception: If node fails after all retries
        """
        existing_artifacts = []
        if preserve_artifacts:
            existing_artifacts = await self.artifact_registry.list_artifacts_by_node(
                project_id=project_id,
                node_id=node.id
            )

        if existing_artifacts and preserve_artifacts:
            logger.info(f"Node {node.id} already has artifacts, skipping execution")
            return {
                "status": "skipped",
                "reason": "artifacts_exist",
                "artifacts": [a.artifact_id for a in existing_artifacts]
            }

        for attempt in range(max_retries):
            try:
                inputs = {
                    **node.inputs,
                    "project_id": project_id,
                    "workspace_id": workspace_id
                }

                result = await self.playbook_runner.start_playbook_execution(
                    playbook_code=node.playbook_code,
                    profile_id=profile_id,
                    workspace_id=workspace_id,
                    inputs=inputs,
                    project_id=project_id
                )

                execution_id = result.get("execution_id") if isinstance(result, dict) else str(result)

                # Try to register artifacts after execution
                try:
                    await self._register_node_artifacts(
                        project_id=project_id,
                        workspace_id=workspace_id,
                        node_id=node.id,
                        execution_id=execution_id,
                        playbook_code=node.playbook_code
                    )
                except Exception as e:
                    logger.warning(f"Failed to register artifacts for node {node.id}: {e}")

                return {
                    "status": "executed",
                    "node_id": node.id,
                    "playbook_code": node.playbook_code,
                    "execution_id": execution_id,
                    "attempt": attempt + 1
                }

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Node {node.id} failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Node {node.id} failed after {max_retries} attempts: {e}")
                    raise

    def _parse_nodes(self, flow_definition: Dict[str, Any]) -> Dict[str, FlowNode]:
        """Parse FlowNode objects from flow definition"""
        nodes = {}
        nodes_data = flow_definition.get("nodes", [])

        for node_data in nodes_data:
            node = FlowNode(**node_data)
            nodes[node.id] = node

        return nodes

    def _build_nodes_from_playbook_sequence(self, playbook_sequence: List[str]) -> Dict[str, FlowNode]:
        """
        Build FlowNode objects from playbook_sequence

        Args:
            playbook_sequence: List of playbook codes

        Returns:
            Dictionary of node_id -> FlowNode
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
                node_type="playbook"
            )
            nodes[node_id] = node
            logger.info(f"Built node {node_id} from playbook_sequence: {playbook_code}")
        return nodes

    def _parse_edges(self, flow_definition: Dict[str, Any]) -> List[FlowEdge]:
        """Parse FlowEdge objects from flow definition"""
        edges_data = flow_definition.get("edges", [])
        return [FlowEdge(**edge_data) for edge_data in edges_data]

    def _get_execution_order(
        self,
        nodes: Dict[str, FlowNode],
        edges: List[FlowEdge],
        completed_nodes: Set[str]
    ) -> List[str]:
        """
        Get topological order of nodes for execution

        Args:
            nodes: Dictionary of node_id -> FlowNode
            edges: List of FlowEdge
            completed_nodes: Set of already completed node IDs

        Returns:
            Ordered list of node IDs to execute
        """
        graph = {node_id: [] for node_id in nodes.keys()}
        in_degree = {node_id: 0 for node_id in nodes.keys()}

        for edge in edges:
            if edge.from_node in nodes and edge.to_node in nodes:
                graph[edge.from_node].append(edge.to_node)
                in_degree[edge.to_node] += 1

        queue = deque([
            node_id for node_id in nodes.keys()
            if in_degree[node_id] == 0 and node_id not in completed_nodes
        ])

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
        resume_from: str
    ) -> Set[str]:
        """
        Get nodes that should be completed before resuming from a specific node

        Args:
            nodes: Dictionary of node_id -> FlowNode
            edges: List of FlowEdge
            resume_from: Node ID to resume from

        Returns:
            Set of node IDs that should be marked as completed
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

    async def _register_node_artifacts(
        self,
        project_id: str,
        workspace_id: str,
        node_id: str,
        execution_id: str,
        playbook_code: str
    ):
        """
        Register artifacts created by a flow node execution

        Attempts to find and register artifacts from playbook execution.
        This is a best-effort operation - artifacts may be registered later
        through other mechanisms.

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
            node_id: Flow node ID
            execution_id: Playbook execution ID
            playbook_code: Playbook code
        """
        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.services.project.project_sandbox_manager import ProjectSandboxManager

            tasks_store = TasksStore(db_path=self.store.db_path)
            task = tasks_store.get_task_by_execution_id(execution_id)

            if not task:
                logger.debug(f"Task not found for execution {execution_id}, skipping artifact registration")
                return

            # Check if task has result with artifact information
            if task.result:
                import json
                if isinstance(task.result, str):
                    try:
                        result_data = json.loads(task.result)
                    except json.JSONDecodeError:
                        result_data = {"content": task.result}
                else:
                    result_data = task.result if isinstance(task.result, dict) else {}

                # Try to extract artifact information from result
                artifacts = result_data.get("artifacts", [])
                if not artifacts and result_data.get("output"):
                    # Single artifact case
                    artifacts = [{"content": result_data.get("output"), "type": "text"}]

                if artifacts:
                    sandbox_manager = ProjectSandboxManager(self.store)
                    sandbox_path = await sandbox_manager.get_sandbox_path(project_id, workspace_id)

                    for i, artifact_data in enumerate(artifacts):
                        artifact_id = artifact_data.get("id") or f"{node_id}_{execution_id}_{i}"
                        artifact_type = artifact_data.get("type", "text")
                        artifact_path = artifact_data.get("path") or f"{node_id}/{artifact_id}.txt"

                        # Write artifact to sandbox if content provided
                        if "content" in artifact_data:
                            full_path = sandbox_path / artifact_path
                            full_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(full_path, "w", encoding="utf-8") as f:
                                f.write(str(artifact_data["content"]))

                        # Register in artifact registry
                        await self.artifact_registry.register_artifact(
                            project_id=project_id,
                            artifact_id=artifact_id,
                            path=artifact_path,
                            artifact_type=artifact_type,
                            created_by=node_id,
                            dependencies=artifact_data.get("dependencies", [])
                        )
                        logger.info(f"Registered artifact {artifact_id} for node {node_id}")

        except Exception as e:
            logger.warning(f"Failed to register artifacts for node {node_id}: {e}", exc_info=True)

    async def _save_flow_checkpoint(
        self,
        project_id: str,
        workspace_id: str,
        flow_id: str,
        current_node: Optional[str],
        completed_nodes: Set[str],
        execution_results: Dict[str, Any],
        failed_node: Optional[str] = None,
        failure_error: Optional[str] = None
    ):
        """
        Save flow execution checkpoint to project metadata

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
            flow_id: Flow ID
            current_node: Current node ID (last executed or failed)
            completed_nodes: Set of completed node IDs
            execution_results: Execution results dictionary
            failed_node: Failed node ID (if any)
            failure_error: Failure error message (if any)
        """
        checkpoint = {
            "flow_id": flow_id,
            "current_node": current_node,
            "completed_nodes": list(completed_nodes),
            "execution_results": execution_results,
            "failed_node": failed_node,
            "failure_error": failure_error,
            "timestamp": _utc_now().isoformat()
        }

        # Try to get profile_id from execution results if not provided
        project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
        if hasattr(project, 'initiator_user_id') and project.initiator_user_id:
            checkpoint["profile_id"] = project.initiator_user_id

        project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
        project.metadata = project.metadata or {}
        project.metadata["flow_checkpoint"] = checkpoint
        await self.project_manager.update_project(project)

        logger.info(f"Saved flow checkpoint for project {project_id}, current_node: {current_node}")

    async def _clear_flow_checkpoint(self, project_id: str, workspace_id: str):
        """
        Clear flow checkpoint from project metadata

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
        """
        project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
        if project.metadata and "flow_checkpoint" in project.metadata:
            del project.metadata["flow_checkpoint"]
            await self.project_manager.update_project(project)
            logger.info(f"Cleared flow checkpoint for project {project_id}")

    async def resume_from_checkpoint(
        self,
        project_id: str,
        workspace_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Resume flow execution from last checkpoint

        Args:
            project_id: Project ID
            workspace_id: Workspace ID

        Returns:
            Execution result if resumed, None if no checkpoint found
        """
        project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
        checkpoint = project.metadata.get("flow_checkpoint") if project.metadata else None

        if not checkpoint:
            logger.info(f"No checkpoint found for project {project_id}")
            return None

        flow_id = checkpoint.get("flow_id")
        failed_node = checkpoint.get("failed_node")
        completed_nodes = set(checkpoint.get("completed_nodes", []))

        if failed_node:
            logger.info(f"Resuming flow from failed node {failed_node}")
            return await self.execute_flow(
                project_id=project_id,
                workspace_id=workspace_id,
                profile_id=checkpoint.get("profile_id"),
                resume_from=failed_node,
                preserve_artifacts=True,
                max_retries=3
            )
        else:
            current_node = checkpoint.get("current_node")
            if current_node:
                logger.info(f"Resuming flow from node {current_node}")
                return await self.execute_flow(
                    project_id=project_id,
                    workspace_id=workspace_id,
                    profile_id=checkpoint.get("profile_id"),
                    resume_from=current_node,
                    preserve_artifacts=True,
                    max_retries=3
                )

        return None
