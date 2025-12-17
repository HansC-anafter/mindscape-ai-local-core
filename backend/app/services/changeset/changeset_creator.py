"""
ChangeSet Creator

Generates change sets from tool execution results or plan outputs.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from backend.app.core.ir.changeset import ChangeSetIR, ChangePatch, ChangeType, ChangeSetStatus

logger = logging.getLogger(__name__)


class ChangeSetCreator:
    """
    Creates change sets from various sources

    Supports creating change sets from:
    - Tool execution results
    - Plan outputs
    - Manual changes
    """

    def __init__(self):
        """Initialize ChangeSetCreator"""
        pass

    def create_from_tool_result(
        self,
        workspace_id: str,
        tool_id: str,
        tool_slot: Optional[str],
        result: Any,
        execution_id: Optional[str] = None,
        plan_id: Optional[str] = None
    ) -> ChangeSetIR:
        """
        Create ChangeSet from tool execution result

        Args:
            workspace_id: Workspace ID
            tool_id: Tool ID that produced the result
            tool_slot: Tool slot (optional)
            result: Tool execution result
            execution_id: Execution ID (optional)
            plan_id: Plan ID (optional)

        Returns:
            ChangeSetIR instance
        """
        changeset_id = str(uuid.uuid4())

        # Convert tool result to change patches
        patches = self._result_to_patches(
            tool_id=tool_id,
            tool_slot=tool_slot,
            result=result
        )

        changeset = ChangeSetIR(
            changeset_id=changeset_id,
            workspace_id=workspace_id,
            patches=patches,
            status=ChangeSetStatus.DRAFT,
            execution_id=execution_id,
            plan_id=plan_id,
            metadata={
                "tool_id": tool_id,
                "tool_slot": tool_slot,
            }
        )

        logger.info(f"ChangeSetCreator: Created changeset {changeset_id} with {len(patches)} patches from tool {tool_id}")
        return changeset

    def create_from_plan_output(
        self,
        workspace_id: str,
        plan_id: str,
        plan_output: Dict[str, Any],
        execution_id: Optional[str] = None
    ) -> ChangeSetIR:
        """
        Create ChangeSet from plan output

        Args:
            workspace_id: Workspace ID
            plan_id: Plan ID
            plan_output: Plan output dictionary
            execution_id: Execution ID (optional)

        Returns:
            ChangeSetIR instance
        """
        changeset_id = str(uuid.uuid4())

        # Convert plan output to change patches
        patches = self._plan_output_to_patches(plan_output)

        changeset = ChangeSetIR(
            changeset_id=changeset_id,
            workspace_id=workspace_id,
            patches=patches,
            status=ChangeSetStatus.DRAFT,
            execution_id=execution_id,
            plan_id=plan_id,
            metadata={
                "source": "plan_output",
            }
        )

        logger.info(f"ChangeSetCreator: Created changeset {changeset_id} with {len(patches)} patches from plan {plan_id}")
        return changeset

    def create_from_patches(
        self,
        workspace_id: str,
        patches: List[ChangePatch],
        execution_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChangeSetIR:
        """
        Create ChangeSet from change patches

        Args:
            workspace_id: Workspace ID
            patches: List of ChangePatch instances
            execution_id: Execution ID (optional)
            plan_id: Plan ID (optional)
            metadata: Additional metadata

        Returns:
            ChangeSetIR instance
        """
        changeset_id = str(uuid.uuid4())

        changeset = ChangeSetIR(
            changeset_id=changeset_id,
            workspace_id=workspace_id,
            patches=patches,
            status=ChangeSetStatus.DRAFT,
            execution_id=execution_id,
            plan_id=plan_id,
            metadata=metadata or {}
        )

        logger.info(f"ChangeSetCreator: Created changeset {changeset_id} with {len(patches)} patches")
        return changeset

    def _result_to_patches(
        self,
        tool_id: str,
        tool_slot: Optional[str],
        result: Any
    ) -> List[ChangePatch]:
        """
        Convert tool result to change patches

        Args:
            tool_id: Tool ID
            tool_slot: Tool slot (optional)
            result: Tool execution result

        Returns:
            List of ChangePatch instances
        """
        patches = []

        # Handle different result types
        if isinstance(result, dict):
            # Dictionary result: treat as structured changes
            for key, value in result.items():
                patch = ChangePatch(
                    change_type=ChangeType.UPDATE,
                    target=tool_slot or tool_id,
                    path=key,
                    new_value=value,
                    metadata={
                        "tool_id": tool_id,
                        "tool_slot": tool_slot,
                    }
                )
                patches.append(patch)
        elif isinstance(result, (str, int, float, bool)):
            # Simple value result: single update patch
            patch = ChangePatch(
                change_type=ChangeType.UPDATE,
                target=tool_slot or tool_id,
                new_value=result,
                metadata={
                    "tool_id": tool_id,
                    "tool_slot": tool_slot,
                }
            )
            patches.append(patch)
        elif isinstance(result, list):
            # List result: multiple create patches
            for i, item in enumerate(result):
                patch = ChangePatch(
                    change_type=ChangeType.CREATE,
                    target=tool_slot or tool_id,
                    path=str(i),
                    new_value=item,
                    metadata={
                        "tool_id": tool_id,
                        "tool_slot": tool_slot,
                        "index": i,
                    }
                )
                patches.append(patch)
        else:
            # Fallback: single update patch
            patch = ChangePatch(
                change_type=ChangeType.UPDATE,
                target=tool_slot or tool_id,
                new_value=str(result),
                metadata={
                    "tool_id": tool_id,
                    "tool_slot": tool_slot,
                }
            )
            patches.append(patch)

        return patches

    def _plan_output_to_patches(self, plan_output: Dict[str, Any]) -> List[ChangePatch]:
        """
        Convert plan output to change patches

        Args:
            plan_output: Plan output dictionary

        Returns:
            List of ChangePatch instances
        """
        patches = []

        # Extract changes from plan output
        # This is a simplified implementation - can be extended based on actual plan output structure
        if "changes" in plan_output:
            for change in plan_output["changes"]:
                change_type = ChangeType(change.get("type", "update"))
                patch = ChangePatch(
                    change_type=change_type,
                    target=change.get("target", "unknown"),
                    path=change.get("path"),
                    old_value=change.get("old_value"),
                    new_value=change.get("new_value"),
                    metadata=change.get("metadata", {})
                )
                patches.append(patch)
        else:
            # Fallback: treat entire plan_output as a single update
            patch = ChangePatch(
                change_type=ChangeType.UPDATE,
                target="plan_output",
                new_value=plan_output,
                metadata={"source": "plan_output"}
            )
            patches.append(patch)

        return patches

