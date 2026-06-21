"""
Flow Executor Service.

Executes PlaybookFlow sequences within a Project context.
"""

import logging
from typing import Any, Dict, Optional

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_checkpoint_manager import (
    PlaybookCheckpointManager,
)
from backend.app.services.playbook_runner import PlaybookRunner
from backend.app.services.project.artifact_registry_service import (
    ArtifactRegistryService,
)
from backend.app.services.project.flow_executor_core import (
    FlowCheckpointMixin,
    FlowGraphMixin,
    FlowNodeExecutionMixin,
)
from backend.app.services.project.project_manager import ProjectManager
from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore

logger = logging.getLogger(__name__)


class FlowExecutionError(Exception):
    """Flow execution error."""


class FlowExecutor(
    FlowNodeExecutionMixin,
    FlowCheckpointMixin,
    FlowGraphMixin,
):
    """Execute PlaybookFlow sequences."""

    def __init__(
        self,
        store: MindscapeStore,
        project_manager: Optional[ProjectManager] = None,
        artifact_registry: Optional[ArtifactRegistryService] = None,
        playbook_runner: Optional[PlaybookRunner] = None,
    ):
        """
        Initialize FlowExecutor.

        Args:
            store: MindscapeStore instance
            project_manager: ProjectManager instance
            artifact_registry: ArtifactRegistryService instance
            playbook_runner: PlaybookRunner instance
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
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Execute a PlaybookFlow for a project.

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
            profile_id: User profile ID for playbook execution
            resume_from: Node ID to resume from
            preserve_artifacts: Whether to preserve existing artifacts
            max_retries: Maximum retry attempts per node

        Returns:
            Execution result with node outcomes

        Raises:
            FlowExecutionError: If flow execution fails
        """
        project = await self.project_manager.get_project(
            project_id,
            workspace_id=workspace_id,
        )
        if not project:
            raise FlowExecutionError(f"Project {project_id} not found")

        flow = self.flows_store.get_flow(project.flow_id)
        if not flow:
            raise FlowExecutionError(f"Flow {project.flow_id} not found")

        nodes = self._parse_nodes(flow.flow_definition)
        if not nodes:
            playbook_sequence = flow.flow_definition.get("playbook_sequence", [])
            if playbook_sequence:
                logger.info(
                    "Flow has no nodes but has playbook_sequence, "
                    f"building nodes from sequence: {playbook_sequence}"
                )
                nodes = self._build_nodes_from_playbook_sequence(playbook_sequence)

        edges = self._parse_edges(flow.flow_definition)

        if resume_from:
            completed_nodes = self._get_completed_nodes_before(
                nodes,
                edges,
                resume_from,
            )
            logger.info(
                f"Resuming flow from node {resume_from}, completed: {completed_nodes}"
            )
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
                        max_retries=max_retries,
                    )
                    execution_results[node_id] = result
                    completed_nodes.add(node_id)

                    await self._save_flow_checkpoint(
                        project_id=project_id,
                        workspace_id=workspace_id,
                        flow_id=flow.id,
                        current_node=node_id,
                        completed_nodes=completed_nodes,
                        execution_results=execution_results,
                    )
                except Exception as exc:
                    logger.error(f"Node {node_id} failed after retries: {exc}")
                    execution_results[node_id] = {
                        "status": "failed",
                        "error": str(exc),
                    }

                    await self._save_flow_checkpoint(
                        project_id=project_id,
                        workspace_id=workspace_id,
                        flow_id=flow.id,
                        current_node=node_id,
                        completed_nodes=completed_nodes,
                        execution_results=execution_results,
                        failed_node=node_id,
                        failure_error=str(exc),
                    )
                    raise FlowExecutionError(
                        f"Flow execution failed at node {node_id}: {exc}"
                    )

            await self._clear_flow_checkpoint(project_id, workspace_id)

            return {
                "project_id": project_id,
                "flow_id": flow.id,
                "completed_nodes": list(completed_nodes),
                "execution_results": execution_results,
                "status": "completed",
            }

        except FlowExecutionError:
            raise
        except Exception as exc:
            logger.error(f"Unexpected error during flow execution: {exc}")
            await self._save_flow_checkpoint(
                project_id=project_id,
                workspace_id=workspace_id,
                flow_id=flow.id,
                current_node=None,
                completed_nodes=completed_nodes,
                execution_results=execution_results,
                failure_error=str(exc),
            )
            raise
