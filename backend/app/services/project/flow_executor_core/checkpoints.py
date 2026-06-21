"""Checkpoint helpers for project flow execution."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class FlowCheckpointMixin:
    """Checkpoint helper methods for FlowExecutor."""

    async def _save_flow_checkpoint(
        self,
        project_id: str,
        workspace_id: str,
        flow_id: str,
        current_node: Optional[str],
        completed_nodes: Set[str],
        execution_results: Dict[str, Any],
        failed_node: Optional[str] = None,
        failure_error: Optional[str] = None,
    ):
        """
        Save a flow execution checkpoint to project metadata.

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
            flow_id: Flow ID
            current_node: Current node ID
            completed_nodes: Completed node IDs
            execution_results: Execution result map
            failed_node: Failed node ID, when available
            failure_error: Failure error message, when available
        """
        checkpoint = {
            "flow_id": flow_id,
            "current_node": current_node,
            "completed_nodes": list(completed_nodes),
            "execution_results": execution_results,
            "failed_node": failed_node,
            "failure_error": failure_error,
            "timestamp": _utc_now().isoformat(),
        }

        project = await self.project_manager.get_project(
            project_id,
            workspace_id=workspace_id,
        )
        if hasattr(project, "initiator_user_id") and project.initiator_user_id:
            checkpoint["profile_id"] = project.initiator_user_id

        project = await self.project_manager.get_project(
            project_id,
            workspace_id=workspace_id,
        )
        project.metadata = project.metadata or {}
        project.metadata["flow_checkpoint"] = checkpoint
        await self.project_manager.update_project(project)

        logger.info(
            f"Saved flow checkpoint for project {project_id}, "
            f"current_node: {current_node}"
        )

    async def _clear_flow_checkpoint(self, project_id: str, workspace_id: str):
        """
        Clear a flow checkpoint from project metadata.

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
        """
        project = await self.project_manager.get_project(
            project_id,
            workspace_id=workspace_id,
        )
        if project.metadata and "flow_checkpoint" in project.metadata:
            del project.metadata["flow_checkpoint"]
            await self.project_manager.update_project(project)
            logger.info(f"Cleared flow checkpoint for project {project_id}")

    async def resume_from_checkpoint(
        self,
        project_id: str,
        workspace_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Resume flow execution from the last checkpoint.

        Args:
            project_id: Project ID
            workspace_id: Workspace ID

        Returns:
            Execution result if resumed, otherwise None
        """
        project = await self.project_manager.get_project(
            project_id,
            workspace_id=workspace_id,
        )
        checkpoint = project.metadata.get("flow_checkpoint") if project.metadata else None

        if not checkpoint:
            logger.info(f"No checkpoint found for project {project_id}")
            return None

        failed_node = checkpoint.get("failed_node")

        if failed_node:
            logger.info(f"Resuming flow from failed node {failed_node}")
            return await self.execute_flow(
                project_id=project_id,
                workspace_id=workspace_id,
                profile_id=checkpoint.get("profile_id"),
                resume_from=failed_node,
                preserve_artifacts=True,
                max_retries=3,
            )

        current_node = checkpoint.get("current_node")
        if current_node:
            logger.info(f"Resuming flow from node {current_node}")
            return await self.execute_flow(
                project_id=project_id,
                workspace_id=workspace_id,
                profile_id=checkpoint.get("profile_id"),
                resume_from=current_node,
                preserve_artifacts=True,
                max_retries=3,
            )

        return None
