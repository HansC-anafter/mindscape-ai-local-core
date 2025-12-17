"""
ChangeSet Pipeline

Unified pipeline for all write operations through ChangeSet.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from backend.app.core.ir.changeset import ChangeSetIR, ChangeSetStatus
from .changeset_creator import ChangeSetCreator
from .sandbox_applier import SandboxApplier
from .diff_generator import DiffGenerator
from .rollback_manager import RollbackManager
from .promotion_manager import PromotionManager
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class ChangeSetPipeline:
    """
    Unified ChangeSet pipeline

    Orchestrates the complete ChangeSet workflow:
    1. CreateChangeSet: Generate changes
    2. ApplyToSandbox: Apply to sandbox, generate preview URL
    3. Diff/Summary: Generate readable diff
    4. RollbackPoint: Create rollback point
    5. PromoteToProd: Promote to production (with human confirmation)
    """

    def __init__(self, store: Optional[MindscapeStore] = None):
        """
        Initialize ChangeSetPipeline

        Args:
            store: MindscapeStore instance (will create if not provided)
        """
        if store is None:
            from backend.app.services.mindscape_store import MindscapeStore
            store = MindscapeStore()

        self.store = store
        self.creator = ChangeSetCreator()
        self.applier = SandboxApplier(store)
        self.diff_generator = DiffGenerator()
        self.rollback_manager = RollbackManager(store)
        self.promotion_manager = PromotionManager()

    async def create_and_apply(
        self,
        workspace_id: str,
        tool_id: str,
        tool_slot: Optional[str],
        result: Any,
        execution_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        sandbox_id: Optional[str] = None,
        sandbox_type: Optional[str] = None,
        auto_create_rollback: bool = True
    ) -> ChangeSetIR:
        """
        Create change set from tool result and apply to sandbox

        Args:
            workspace_id: Workspace ID
            tool_id: Tool ID that produced the result
            tool_slot: Tool slot (optional)
            result: Tool execution result
            execution_id: Execution ID (optional)
            plan_id: Plan ID (optional)
            sandbox_id: Sandbox ID (will create if not provided)
            sandbox_type: Sandbox type (required if sandbox_id not provided)
            auto_create_rollback: Whether to automatically create rollback point

        Returns:
            ChangeSetIR instance with preview_url and diff
        """
        try:
            # 1. Create change set
            changeset = self.creator.create_from_tool_result(
                workspace_id=workspace_id,
                tool_id=tool_id,
                tool_slot=tool_slot,
                result=result,
                execution_id=execution_id,
                plan_id=plan_id
            )

            # 2. Apply to sandbox
            changeset = await self.applier.apply_to_sandbox(
                changeset=changeset,
                sandbox_id=sandbox_id,
                sandbox_type=sandbox_type
            )

            # 3. Generate diff
            diff_result = self.diff_generator.generate_diff(changeset)
            changeset.diff_summary = diff_result["diff_summary"]
            changeset.diff_details = diff_result["diff_details"]

            # 4. Create rollback point (if requested)
            if auto_create_rollback and changeset.preview_url:
                try:
                    # Get sandbox_id from changeset metadata or use the one we created
                    if not sandbox_id:
                        # Extract from preview_url or use a default
                        sandbox_id = changeset.metadata.get("sandbox_id") if changeset.metadata else None

                    if sandbox_id:
                        await self.rollback_manager.create_rollback_point(changeset, sandbox_id)
                except Exception as e:
                    logger.warning(f"ChangeSetPipeline: Failed to create rollback point: {e}", exc_info=True)

            # 5. Update status to pending review
            changeset.status = ChangeSetStatus.PENDING_REVIEW

            logger.info(f"ChangeSetPipeline: Created and applied changeset {changeset.changeset_id}")
            return changeset

        except Exception as e:
            logger.error(f"ChangeSetPipeline: Failed to create and apply changeset: {e}", exc_info=True)
            raise

    async def approve_and_promote(
        self,
        changeset: ChangeSetIR,
        approved_by: str,
        target_system: str,
        promoted_by: Optional[str] = None,
        approval_notes: Optional[str] = None,
        promotion_notes: Optional[str] = None
    ) -> ChangeSetIR:
        """
        Approve and promote change set to production

        Args:
            changeset: ChangeSetIR instance
            approved_by: User ID who approved
            target_system: Target system identifier
            promoted_by: User ID who promoted (defaults to approved_by)
            approval_notes: Approval notes (optional)
            promotion_notes: Promotion notes (optional)

        Returns:
            Updated ChangeSetIR with status PROMOTED_TO_PROD

        Note:
            This method enforces the rule: only allowed with human confirmation.
        """
        try:
            # 1. Approve (human confirmation)
            changeset = await self.promotion_manager.approve(
                changeset=changeset,
                approved_by=approved_by,
                notes=approval_notes
            )

            # 2. Promote to production
            changeset = await self.promotion_manager.promote_to_prod(
                changeset=changeset,
                promoted_by=promoted_by or approved_by,
                target_system=target_system,
                notes=promotion_notes
            )

            logger.info(f"ChangeSetPipeline: Approved and promoted changeset {changeset.changeset_id} to {target_system}")
            return changeset

        except Exception as e:
            logger.error(f"ChangeSetPipeline: Failed to approve and promote changeset: {e}", exc_info=True)
            raise

    async def rollback_changeset(
        self,
        changeset: ChangeSetIR
    ) -> ChangeSetIR:
        """
        Rollback a change set

        Args:
            changeset: ChangeSetIR instance with rollback_point_id

        Returns:
            Updated ChangeSetIR with status ROLLED_BACK
        """
        try:
            changeset = await self.rollback_manager.rollback(changeset)
            logger.info(f"ChangeSetPipeline: Rolled back changeset {changeset.changeset_id}")
            return changeset
        except Exception as e:
            logger.error(f"ChangeSetPipeline: Failed to rollback changeset: {e}", exc_info=True)
            raise

    async def reject_changeset(
        self,
        changeset: ChangeSetIR,
        rejected_by: str,
        reason: Optional[str] = None
    ) -> ChangeSetIR:
        """
        Reject a change set

        Args:
            changeset: ChangeSetIR instance
            rejected_by: User ID who rejected
            reason: Rejection reason (optional)

        Returns:
            Updated ChangeSetIR with status REJECTED
        """
        try:
            changeset = await self.promotion_manager.reject(
                changeset=changeset,
                rejected_by=rejected_by,
                reason=reason
            )
            logger.info(f"ChangeSetPipeline: Rejected changeset {changeset.changeset_id}")
            return changeset
        except Exception as e:
            logger.error(f"ChangeSetPipeline: Failed to reject changeset: {e}", exc_info=True)
            raise

