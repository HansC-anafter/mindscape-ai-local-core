"""
Handoff Registry Store — DB access layer for idempotency checks.

Wraps INSERT into `handoff_registry` with unique-constraint handling.
Uses the repo's standard SessionLocalCore factory for DB access.
"""

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


class HandoffRegistryStore:
    """Thin store layer for the ``handoff_registry`` table.

    Usage::

        store = HandoffRegistryStore()
        ok = store.register_attempt(
            idempotency_key="task:phase:1",
            task_ir_id="task-uuid",
            phase_id="phase-uuid",
            attempt_number=1,
        )
        if not ok:
            # duplicate dispatch detected — MUST abort
    """

    def register_attempt(
        self,
        *,
        idempotency_key: str,
        task_ir_id: str,
        phase_id: str,
        attempt_number: int = 1,
    ) -> Optional[bool]:
        """Register a dispatch attempt.

        Returns True on success, False only when the idempotency key is an
        explicit duplicate, and None when the registry is unavailable or hits an
        unexpected DB error. Callers should fail open on None.
        """
        try:
            from app.database.engine import SessionLocalCore
            from backend.app.models.handoff_registry import HandoffRegistry

            if SessionLocalCore is None:
                logger.error(
                    "HandoffRegistry: SessionLocalCore is None — "
                    "DB not configured; allowing dispatch without registry"
                )
                return None

            session = SessionLocalCore()
            try:
                row = HandoffRegistry(
                    id=str(uuid.uuid4()),
                    idempotency_key=idempotency_key,
                    task_ir_id=task_ir_id,
                    phase_id=phase_id,
                    attempt_number=attempt_number,
                    status="dispatched",
                )
                session.add(row)
                session.commit()
                logger.info(
                    "HandoffRegistry: registered key=%s", idempotency_key
                )
                return True
            except Exception as exc:
                session.rollback()
                exc_str = str(exc).lower()
                if "unique" in exc_str or "duplicate" in exc_str or "integrity" in exc_str:
                    logger.warning(
                        "HandoffRegistry: duplicate key=%s (idempotency block)",
                        idempotency_key,
                    )
                    return False
                logger.error(
                    "HandoffRegistry: unexpected DB error for key=%s — "
                    "allowing dispatch without registry: %s",
                    idempotency_key,
                    exc,
                )
                return None
            finally:
                session.close()
        except ImportError as exc:
            logger.error(
                "HandoffRegistry: import failed — allowing dispatch without registry: %s",
                exc,
            )
            return None
        except Exception as exc:
            logger.error(
                "HandoffRegistry: session setup failed — "
                "allowing dispatch without registry: %s",
                exc,
            )
            return None

    def update_status(
        self,
        idempotency_key: str,
        status: str,
    ) -> None:
        """Update the status of an existing registry entry."""
        try:
            from app.database.engine import SessionLocalCore
            from backend.app.models.handoff_registry import HandoffRegistry

            if SessionLocalCore is None:
                return

            session = SessionLocalCore()
            try:
                row = (
                    session.query(HandoffRegistry)
                    .filter_by(idempotency_key=idempotency_key)
                    .first()
                )
                if row:
                    row.status = status
                    session.commit()
            except Exception as exc:
                session.rollback()
                logger.warning(
                    "HandoffRegistry: status update failed key=%s: %s",
                    idempotency_key,
                    exc,
                )
            finally:
                session.close()
        except Exception as exc:
            logger.warning(
                "HandoffRegistry: status update setup failed key=%s: %s",
                idempotency_key,
                exc,
            )

    def mark_completed(
        self,
        *,
        task_ir_id: str,
        execution_id: str,
        artifact_id: Optional[str] = None,
    ) -> None:
        """Mark all dispatches for a task_ir_id as completed.

        Links the dispatch record to the landing result by storing
        ``execution_id`` and ``artifact_id`` for provenance tracing.

        Non-fatal: errors are logged but never raised.
        """
        try:
            from app.database.engine import SessionLocalCore
            from backend.app.models.handoff_registry import HandoffRegistry
            from sqlalchemy.sql import func

            if SessionLocalCore is None:
                return

            session = SessionLocalCore()
            try:
                rows = (
                    session.query(HandoffRegistry)
                    .filter_by(task_ir_id=task_ir_id, status="dispatched")
                    .all()
                )
                for row in rows:
                    row.status = "completed"
                    row.execution_id = execution_id
                    row.artifact_id = artifact_id
                    row.completed_at = func.now()
                if rows:
                    session.commit()
                    logger.info(
                        "HandoffRegistry: marked %d entries completed for task_ir=%s exec=%s art=%s",
                        len(rows),
                        task_ir_id,
                        execution_id,
                        artifact_id,
                    )
            except Exception as exc:
                session.rollback()
                logger.warning(
                    "HandoffRegistry: mark_completed failed task_ir=%s: %s",
                    task_ir_id,
                    exc,
                )
            finally:
                session.close()
        except Exception as exc:
            logger.warning(
                "HandoffRegistry: mark_completed setup failed: %s", exc
            )
