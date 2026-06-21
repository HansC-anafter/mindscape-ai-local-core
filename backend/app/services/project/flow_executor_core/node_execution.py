"""Node execution and artifact registration helpers for project flows."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from backend.app.models.playbook_flow import FlowNode

logger = logging.getLogger(__name__)


class FlowNodeExecutionMixin:
    """Node execution helper methods for FlowExecutor."""

    async def _execute_node_with_retry(
        self,
        node: FlowNode,
        project_id: str,
        workspace_id: str,
        profile_id: str,
        preserve_artifacts: bool,
        max_retries: int,
    ) -> Dict[str, Any]:
        """
        Execute a flow node with retry logic.

        Args:
            node: FlowNode to execute
            project_id: Project ID
            workspace_id: Workspace ID
            profile_id: User profile ID
            preserve_artifacts: Whether to preserve existing artifacts
            max_retries: Maximum retry attempts

        Returns:
            Node execution result
        """
        existing_artifacts = []
        if preserve_artifacts:
            existing_artifacts = await self.artifact_registry.list_artifacts_by_node(
                project_id=project_id,
                node_id=node.id,
            )

        if existing_artifacts and preserve_artifacts:
            logger.info(f"Node {node.id} already has artifacts, skipping execution")
            return {
                "status": "skipped",
                "reason": "artifacts_exist",
                "artifacts": [a.artifact_id for a in existing_artifacts],
            }

        for attempt in range(max_retries):
            try:
                inputs = {
                    **node.inputs,
                    "project_id": project_id,
                    "workspace_id": workspace_id,
                }

                result = await self.playbook_runner.start_playbook_execution(
                    playbook_code=node.playbook_code,
                    profile_id=profile_id,
                    workspace_id=workspace_id,
                    inputs=inputs,
                    project_id=project_id,
                )

                execution_id = result.get("execution_id") if isinstance(result, dict) else str(result)

                try:
                    await self._register_node_artifacts(
                        project_id=project_id,
                        workspace_id=workspace_id,
                        node_id=node.id,
                        execution_id=execution_id,
                        playbook_code=node.playbook_code,
                    )
                except Exception as exc:
                    logger.warning(
                        f"Failed to register artifacts for node {node.id}: {exc}"
                    )

                return {
                    "status": "executed",
                    "node_id": node.id,
                    "playbook_code": node.playbook_code,
                    "execution_id": execution_id,
                    "attempt": attempt + 1,
                }

            except Exception as exc:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Node {node.id} failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {wait_time}s: {exc}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Node {node.id} failed after {max_retries} attempts: {exc}"
                    )
                    raise
    async def _register_node_artifacts(
        self,
        project_id: str,
        workspace_id: str,
        node_id: str,
        execution_id: str,
        playbook_code: str,
    ):
        """
        Register artifacts created by a flow node execution.

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
            node_id: Flow node ID
            execution_id: Playbook execution ID
            playbook_code: Playbook code
        """
        try:
            from backend.app.services.project.project_sandbox_manager import (
                ProjectSandboxManager,
            )
            from backend.app.services.stores.tasks_store import TasksStore

            tasks_store = TasksStore()
            task = tasks_store.get_task_by_execution_id(execution_id)

            if not task:
                logger.debug(
                    f"Task not found for execution {execution_id}, "
                    "skipping artifact registration"
                )
                return

            if task.result:
                if isinstance(task.result, str):
                    try:
                        result_data = json.loads(task.result)
                    except json.JSONDecodeError:
                        result_data = {"content": task.result}
                else:
                    result_data = task.result if isinstance(task.result, dict) else {}

                artifacts = result_data.get("artifacts", [])
                if not artifacts and result_data.get("output"):
                    artifacts = [{"content": result_data.get("output"), "type": "text"}]

                if artifacts:
                    sandbox_manager = ProjectSandboxManager(self.store)
                    sandbox_path = await sandbox_manager.get_sandbox_path(
                        project_id,
                        workspace_id,
                    )

                    for i, artifact_data in enumerate(artifacts):
                        artifact_id = artifact_data.get("id") or f"{node_id}_{execution_id}_{i}"
                        artifact_type = artifact_data.get("type", "text")
                        artifact_path = artifact_data.get("path") or f"{node_id}/{artifact_id}.txt"

                        if "content" in artifact_data:
                            full_path = sandbox_path / artifact_path
                            full_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(full_path, "w", encoding="utf-8") as file:
                                file.write(str(artifact_data["content"]))

                        await self.artifact_registry.register_artifact(
                            project_id=project_id,
                            artifact_id=artifact_id,
                            path=artifact_path,
                            artifact_type=artifact_type,
                            created_by=node_id,
                            dependencies=artifact_data.get("dependencies", []),
                        )
                        logger.info(
                            f"Registered artifact {artifact_id} for node {node_id}"
                        )

        except Exception as exc:
            logger.warning(
                f"Failed to register artifacts for node {node_id}: {exc}",
                exc_info=True,
            )
