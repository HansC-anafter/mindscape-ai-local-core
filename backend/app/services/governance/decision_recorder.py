"""
Governance Decision Recorder

Records governance decisions to database for Cloud environment.
"""

import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class GovernanceDecisionRecorder:
    """Service for recording governance decisions to database"""

    def __init__(self, db_connection=None):
        """
        Initialize GovernanceDecisionRecorder

        Args:
            db_connection: Database connection (None for Local-Core)
        """
        self.db_connection = db_connection

    def _is_cloud_environment(self) -> bool:
        """Check if running in Cloud environment"""
        return self.db_connection is not None

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
        if not self._is_cloud_environment():
            # Local-Core: Don't record (no database)
            return None

        try:
            decision_id = str(uuid.uuid4())
            timestamp = datetime.utcnow().isoformat()

            # Prepare metadata as JSON string
            metadata_json = None
            if metadata:
                import json
                metadata_json = json.dumps(metadata)

            # Insert into database
            # Support both SQLite and PostgreSQL
            if hasattr(self.db_connection, 'execute'):
                # SQLite
                query = """
                    INSERT INTO governance_decisions (
                        decision_id, workspace_id, execution_id, timestamp,
                        layer, approved, reason, playbook_code, metadata,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                params = (
                    decision_id, workspace_id, execution_id, timestamp,
                    layer, 1 if approved else 0, reason, playbook_code, metadata_json,
                    timestamp, timestamp
                )
                cursor = self.db_connection.cursor()
                cursor.execute(query, params)
                self.db_connection.commit()
            else:
                # PostgreSQL (using parameterized query)
                query = """
                    INSERT INTO governance_decisions (
                        decision_id, workspace_id, execution_id, timestamp,
                        layer, approved, reason, playbook_code, metadata,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = (
                    decision_id, workspace_id, execution_id, timestamp,
                    layer, approved, reason, playbook_code, metadata_json,
                    timestamp, timestamp
                )
                cursor = self.db_connection.cursor()
                cursor.execute(query, params)
                self.db_connection.commit()

            logger.info(f"Recorded governance decision: {decision_id} for layer {layer}")
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
        # Check if database connection is available (Local-Core SQLite or Cloud PostgreSQL)
        if not self.db_connection:
            # No database connection available, skip recording
            return None

        try:
            usage_id = str(uuid.uuid4())
            date = datetime.utcnow().date().isoformat()
            timestamp = datetime.utcnow().isoformat()

            # Insert into database
            # Support both SQLite and PostgreSQL
            if hasattr(self.db_connection, 'execute'):
                # SQLite
                query = """
                    INSERT INTO cost_usage (
                        id, workspace_id, execution_id, date, cost,
                        playbook_code, model_name, token_count,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                params = (
                    usage_id, workspace_id, execution_id, date, cost,
                    playbook_code, model_name, token_count,
                    timestamp, timestamp
                )
                cursor = self.db_connection.cursor()
                cursor.execute(query, params)
                self.db_connection.commit()
            else:
                # PostgreSQL
                query = """
                    INSERT INTO cost_usage (
                        id, workspace_id, execution_id, date, cost,
                        playbook_code, model_name, token_count,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = (
                    usage_id, workspace_id, execution_id, date, cost,
                    playbook_code, model_name, token_count,
                    timestamp, timestamp
                )
                cursor = self.db_connection.cursor()
                cursor.execute(query, params)
                self.db_connection.commit()

            logger.info(f"Recorded cost usage: {usage_id} for workspace {workspace_id}")
            return usage_id

        except Exception as e:
            logger.error(f"Failed to record cost usage: {e}", exc_info=True)
            return None

