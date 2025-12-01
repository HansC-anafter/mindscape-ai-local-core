"""
StageResults Store Service

Handles storage and retrieval of StageResult records for playbook execution tracking.
"""

import json
import sqlite3
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

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
        created_at: datetime
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


class StageResultsStore:
    """Store for StageResult records"""

    def __init__(self, db_path: str):
        """
        Initialize StageResultsStore

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def create_stage_result(self, stage_result: StageResult) -> StageResult:
        """
        Create a new StageResult record

        Args:
            stage_result: StageResult instance

        Returns:
            Created StageResult
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT INTO stage_results (
                        id, execution_id, step_id, stage_name, result_type,
                        content, preview, requires_review, review_status,
                        artifact_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stage_result.id,
                    stage_result.execution_id,
                    stage_result.step_id,
                    stage_result.stage_name,
                    stage_result.result_type,
                    json.dumps(stage_result.content),
                    stage_result.preview,
                    1 if stage_result.requires_review else 0,
                    stage_result.review_status,
                    stage_result.artifact_id,
                    stage_result.created_at.isoformat()
                ))

                conn.commit()
                logger.debug(f"Created StageResult {stage_result.id} for stage {stage_result.stage_name}")
                return stage_result
        except Exception as e:
            logger.error(f"Failed to create StageResult: {e}", exc_info=True)
            raise

    def get_stage_result(self, stage_result_id: str) -> Optional[StageResult]:
        """Get StageResult by ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute('SELECT * FROM stage_results WHERE id = ?', (stage_result_id,))
                row = cursor.fetchone()

                if not row:
                    return None

                return self._row_to_stage_result(row)
        except Exception as e:
            logger.error(f"Failed to get StageResult {stage_result_id}: {e}", exc_info=True)
            return None

    def list_stage_results(
        self,
        execution_id: Optional[str] = None,
        step_id: Optional[str] = None,
        limit: int = 100
    ) -> List[StageResult]:
        """List StageResults with filters"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                query = 'SELECT * FROM stage_results WHERE 1=1'
                params = []

                if execution_id:
                    query += ' AND execution_id = ?'
                    params.append(execution_id)
                if step_id:
                    query += ' AND step_id = ?'
                    params.append(step_id)

                query += ' ORDER BY created_at DESC LIMIT ?'
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [self._row_to_stage_result(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list StageResults: {e}", exc_info=True)
            return []

    def _row_to_stage_result(self, row: sqlite3.Row) -> StageResult:
        """Convert database row to StageResult"""
        content = {}
        if row['content']:
            try:
                content = json.loads(row['content'])
            except Exception:
                pass

        return StageResult(
            id=row['id'],
            execution_id=row['execution_id'],
            step_id=row['step_id'],
            stage_name=row['stage_name'],
            result_type=row['result_type'],
            content=content,
            preview=row['preview'],
            requires_review=bool(row['requires_review']),
            review_status=row['review_status'],
            artifact_id=row['artifact_id'],
            created_at=datetime.fromisoformat(row['created_at'])
        )

