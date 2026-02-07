"""
StageResults Store Service

Handles storage and retrieval of StageResult records for playbook execution tracking.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class StageResult:
    """StageResult model for database operations"""

    def __init__(
        self,
        id: str,
        execution_id: str,
        step_id: Optional[str],
        stage_name: str,
        result_type: str,
        content: Dict[str, Any],
        preview: Optional[str],
        requires_review: bool,
        review_status: Optional[str],
        artifact_id: Optional[str],
        created_at: datetime,
    ):
        self.id = id
        self.execution_id = execution_id
        self.step_id = step_id
        self.stage_name = stage_name
        self.result_type = result_type
        self.content = content
        self.preview = preview
        self.requires_review = requires_review
        self.review_status = review_status
        self.artifact_id = artifact_id
        self.created_at = created_at


class StageResultsStore(PostgresStoreBase):
    """Store for StageResult records (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def create_stage_result(self, stage_result: StageResult) -> StageResult:
        """Create a new StageResult record"""
        try:
            with self.transaction() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO stage_results (
                            id, execution_id, step_id, stage_name, result_type,
                            content, preview, requires_review, review_status,
                            artifact_id, created_at
                        ) VALUES (
                            :id, :execution_id, :step_id, :stage_name, :result_type,
                            :content, :preview, :requires_review, :review_status,
                            :artifact_id, :created_at
                        )
                    """
                    ),
                    {
                        "id": stage_result.id,
                        "execution_id": stage_result.execution_id,
                        "step_id": stage_result.step_id,
                        "stage_name": stage_result.stage_name,
                        "result_type": stage_result.result_type,
                        "content": self.serialize_json(stage_result.content),
                        "preview": stage_result.preview,
                        "requires_review": stage_result.requires_review,
                        "review_status": stage_result.review_status,
                        "artifact_id": stage_result.artifact_id,
                        "created_at": stage_result.created_at,
                    },
                )
                logger.debug(
                    f"Created StageResult {stage_result.id} for stage {stage_result.stage_name}"
                )
                return stage_result
        except Exception as e:
            logger.error(f"Failed to create StageResult: {e}", exc_info=True)
            raise

    def get_stage_result(self, stage_result_id: str) -> Optional[StageResult]:
        """Get StageResult by ID"""
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    text("SELECT * FROM stage_results WHERE id = :id"),
                    {"id": stage_result_id},
                ).fetchone()
                if not row:
                    return None
                return self._row_to_stage_result(row)
        except Exception as e:
            logger.error(
                f"Failed to get StageResult {stage_result_id}: {e}", exc_info=True
            )
            return None

    def list_stage_results(
        self,
        execution_id: Optional[str] = None,
        step_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[StageResult]:
        """List StageResults with filters"""
        try:
            with self.get_connection() as conn:
                query = "SELECT * FROM stage_results WHERE 1=1"
                params: Dict[str, Any] = {"limit": limit}

                if execution_id:
                    query += " AND execution_id = :execution_id"
                    params["execution_id"] = execution_id
                if step_id:
                    query += " AND step_id = :step_id"
                    params["step_id"] = step_id

                query += " ORDER BY created_at DESC LIMIT :limit"

                rows = conn.execute(text(query), params).fetchall()
                return [self._row_to_stage_result(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list StageResults: {e}", exc_info=True)
            return []

    def _row_to_stage_result(self, row) -> StageResult:
        """Convert database row to StageResult"""
        data = row._mapping if hasattr(row, "_mapping") else row
        return StageResult(
            id=data["id"],
            execution_id=data["execution_id"],
            step_id=data["step_id"],
            stage_name=data["stage_name"],
            result_type=data["result_type"],
            content=self.deserialize_json(data["content"], {}),
            preview=data["preview"],
            requires_review=bool(data["requires_review"]),
            review_status=data["review_status"],
            artifact_id=data["artifact_id"],
            created_at=data["created_at"],
        )
