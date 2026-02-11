"""
Promotion Manager

Manages promotion of change sets to production (only with human confirmation).
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from backend.app.core.ir.changeset import ChangeSetIR, ChangeSetStatus

logger = logging.getLogger(__name__)


class PromotionManager:
    """
    Manages promotion of change sets to production

    Write rule: Only allowed with human confirmation.
    """

    def __init__(self):
        """Initialize PromotionManager"""
        pass

    async def approve(
        self,
        changeset: ChangeSetIR,
        approved_by: str,
        notes: Optional[str] = None
    ) -> ChangeSetIR:
        """
        Approve a change set (human confirmation)

        Args:
            changeset: ChangeSetIR instance
            approved_by: User ID who approved
            notes: Approval notes (optional)

        Returns:
            Updated ChangeSetIR with status APPROVED
        """
        try:
            # Validate that changeset is in a state that can be approved
            if changeset.status not in [ChangeSetStatus.APPLIED_TO_SANDBOX, ChangeSetStatus.PENDING_REVIEW]:
                raise ValueError(f"Cannot approve changeset in status {changeset.status.value}")

            # Update changeset
            changeset.status = ChangeSetStatus.APPROVED
            changeset.approved_by = approved_by
            changeset.approved_at = _utc_now()

            if notes:
                if not changeset.metadata:
                    changeset.metadata = {}
                changeset.metadata["approval_notes"] = notes

            logger.info(f"PromotionManager: Approved changeset {changeset.changeset_id} by {approved_by}")
            return changeset

        except Exception as e:
            logger.error(f"PromotionManager: Failed to approve changeset: {e}", exc_info=True)
            raise

    async def promote_to_prod(
        self,
        changeset: ChangeSetIR,
        promoted_by: str,
        target_system: str,
        notes: Optional[str] = None
    ) -> ChangeSetIR:
        """
        Promote change set to production (only allowed if approved)

        Args:
            changeset: ChangeSetIR instance (must be APPROVED)
            promoted_by: User ID who promoted
            target_system: Target system identifier (e.g., "wordpress", "headless", "filesystem")
            notes: Promotion notes (optional)

        Returns:
            Updated ChangeSetIR with status PROMOTED_TO_PROD

        Raises:
            ValueError: If changeset is not approved
        """
        try:
            # Validate that changeset is approved
            if changeset.status != ChangeSetStatus.APPROVED:
                raise ValueError(
                    f"Cannot promote changeset in status {changeset.status.value}. "
                    f"Changeset must be APPROVED before promotion to production."
                )

            # Validate human confirmation (approved_by must be set)
            if not changeset.approved_by:
                raise ValueError(
                    "Cannot promote changeset without human approval. "
                    "Changeset must be approved by a human user before promotion."
                )

            # Apply changes to production system
            await self._apply_to_production(changeset, target_system)

            # Update changeset
            changeset.status = ChangeSetStatus.PROMOTED_TO_PROD
            changeset.promoted_at = _utc_now()

            if not changeset.metadata:
                changeset.metadata = {}
            changeset.metadata["promoted_by"] = promoted_by
            changeset.metadata["target_system"] = target_system
            if notes:
                changeset.metadata["promotion_notes"] = notes

            logger.info(f"PromotionManager: Promoted changeset {changeset.changeset_id} to {target_system} by {promoted_by}")
            return changeset

        except Exception as e:
            logger.error(f"PromotionManager: Failed to promote changeset: {e}", exc_info=True)
            raise

    async def reject(
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
            changeset.status = ChangeSetStatus.REJECTED

            if not changeset.metadata:
                changeset.metadata = {}
            changeset.metadata["rejected_by"] = rejected_by
            if reason:
                changeset.metadata["rejection_reason"] = reason

            logger.info(f"PromotionManager: Rejected changeset {changeset.changeset_id} by {rejected_by}")
            return changeset

        except Exception as e:
            logger.error(f"PromotionManager: Failed to reject changeset: {e}", exc_info=True)
            raise

    async def _apply_to_production(
        self,
        changeset: ChangeSetIR,
        target_system: str
    ) -> None:
        """
        Apply changes to production system

        Args:
            changeset: ChangeSetIR instance
            target_system: Target system identifier

        Note:
            This is a placeholder implementation.
            Actual production application should be implemented per target system.
        """
        logger.info(f"PromotionManager: Applying changeset {changeset.changeset_id} to {target_system}")

        # Placeholder: Actual implementation depends on target system
        # For WordPress: use wordpress_sync service
        # For Headless: use headless API
        # For Filesystem: use filesystem tools

        if target_system == "wordpress":
            # TODO: Integrate with wordpress_sync service
            logger.info(f"PromotionManager: Would apply to WordPress (not yet implemented)")
        elif target_system == "headless":
            # TODO: Integrate with headless API
            logger.info(f"PromotionManager: Would apply to Headless (not yet implemented)")
        elif target_system == "filesystem":
            # TODO: Integrate with filesystem tools
            logger.info(f"PromotionManager: Would apply to Filesystem (not yet implemented)")
        else:
            logger.warning(f"PromotionManager: Unknown target system {target_system}, skipping production application")










