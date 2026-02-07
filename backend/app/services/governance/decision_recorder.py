"""
Governance Decision Recorder

Records governance decisions to database for Cloud environment.
"""

import logging
from typing import Optional, Dict, Any

from backend.app.services.governance.governance_store import GovernanceStore

logger = logging.getLogger(__name__)


class GovernanceDecisionRecorder:
    """Service for recording governance decisions to database"""

    def __init__(self, store: Optional[GovernanceStore] = None):
        """
        Initialize GovernanceDecisionRecorder

        Args:
            store: GovernanceStore instance (optional)
        """
        self.store = store or GovernanceStore()

    async def record_decision(
        self,
        workspace_id: str,
        execution_id: Optional[str],
        layer: str,
        approved: bool,
        reason: Optional[str] = None,
        playbook_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Record governance decision to database

        Args:
            workspace_id: Workspace ID
            execution_id: Execution ID (optional)
            layer: Governance layer ('cost', 'node', 'policy', 'preflight')
            approved: Whether decision was approved
            reason: Rejection reason (if not approved)
            playbook_code: Playbook code
            metadata: Additional metadata

        Returns:
            Decision ID if recorded, None otherwise
        """
        try:
            decision_id = self.store.record_decision(
                workspace_id=workspace_id,
                execution_id=execution_id,
                layer=layer,
                approved=approved,
                reason=reason,
                playbook_code=playbook_code,
                metadata=metadata,
            )
            logger.info(
                "Recorded governance decision: %s for layer %s", decision_id, layer
            )
            return decision_id

        except Exception as e:
            logger.error(f"Failed to record governance decision: {e}", exc_info=True)
            return None

    async def record_cost_usage(
        self,
        workspace_id: str,
        execution_id: Optional[str],
        cost: float,
        playbook_code: Optional[str] = None,
        model_name: Optional[str] = None,
        token_count: Optional[int] = None
    ) -> Optional[str]:
        """
        Record cost usage to database

        Args:
            workspace_id: Workspace ID
            execution_id: Execution ID (optional)
            cost: Cost in USD
            playbook_code: Playbook code
            model_name: Model name
            token_count: Token count

        Returns:
            Cost usage ID if recorded, None otherwise
        """
        try:
            usage_id = self.store.record_cost_usage(
                workspace_id=workspace_id,
                execution_id=execution_id,
                cost=cost,
                playbook_code=playbook_code,
                model_name=model_name,
                token_count=token_count,
            )
            logger.info(
                "Recorded cost usage: %s for workspace %s", usage_id, workspace_id
            )
            return usage_id

        except Exception as e:
            logger.error(f"Failed to record cost usage: {e}", exc_info=True)
            return None
