"""SQL owner for durable projection task/source admission receipts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

from .internal_admission import InternalProjectionAdmissionReceipt


_INTERNAL_PROJECTION_TOOL = "knowledge.project_source"


class InternalProjectionAdmissionStore(PostgresStoreBase):
    """Persist and verify the task-to-intake proof created in one transaction."""

    def record_with_conn(
        self,
        conn: Any,
        receipt: InternalProjectionAdmissionReceipt,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO knowledge_projection_task_admissions (
                    task_id, intake_id, receipt_hash, trigger_mode,
                    source_ordinal, source_instance_id, source_revision,
                    content_hash
                ) VALUES (
                    :task_id, :intake_id, :receipt_hash, :trigger_mode,
                    :source_ordinal, :source_instance_id, :source_revision,
                    :content_hash
                )
                ON CONFLICT (task_id, intake_id) DO NOTHING
                """
            ),
            [
                {
                    "task_id": receipt.task_id,
                    "intake_id": binding.intake_id,
                    "receipt_hash": receipt.receipt_hash,
                    "trigger_mode": receipt.trigger_mode,
                    "source_ordinal": ordinal,
                    "source_instance_id": binding.source_instance_id,
                    "source_revision": binding.source_revision,
                    "content_hash": binding.content_hash,
                }
                for ordinal, binding in enumerate(receipt.sources)
            ],
        )
        if not self._verify_with_conn(conn, receipt):
            raise RuntimeError(
                "knowledge_projection_task_admission_conflict"
            )

    def verify(
        self,
        receipt: InternalProjectionAdmissionReceipt,
    ) -> bool:
        with self.transaction() as conn:
            return self._verify_with_conn(conn, receipt)

    @staticmethod
    def _verify_with_conn(
        conn: Any,
        receipt: InternalProjectionAdmissionReceipt,
    ) -> bool:
        rows = conn.execute(
            text(
                """
                SELECT
                    admission.task_id,
                    admission.intake_id,
                    admission.receipt_hash,
                    admission.trigger_mode,
                    admission.source_ordinal,
                    admission.source_instance_id,
                    admission.source_revision,
                    admission.content_hash,
                    intake.source_instance_id AS intake_source_instance_id,
                    intake.source_revision AS intake_source_revision,
                    intake.content_hash AS intake_content_hash,
                    task.workspace_id,
                    task.execution_id,
                    task.pack_id,
                    task.task_type,
                    task.execution_context
                FROM knowledge_projection_task_admissions AS admission
                JOIN knowledge_source_intakes AS intake
                  ON intake.id = admission.intake_id
                JOIN tasks AS task
                  ON task.id = admission.task_id
                WHERE admission.task_id = :task_id
                ORDER BY admission.source_ordinal
                """
            ),
            {"task_id": receipt.task_id},
        ).fetchall()
        if len(rows) != len(receipt.sources):
            return False
        expected_receipt = receipt.model_dump(mode="json")
        for ordinal, (row, binding) in enumerate(
            zip(rows, receipt.sources)
        ):
            context = row[15] if isinstance(row[15], dict) else {}
            if (
                str(row[0]) != receipt.task_id
                or str(row[1]) != binding.intake_id
                or str(row[2]) != receipt.receipt_hash
                or str(row[3]) != receipt.trigger_mode
                or int(row[4]) != ordinal
                or str(row[5]) != binding.source_instance_id
                or str(row[6]) != binding.source_revision
                or str(row[7]) != binding.content_hash
                or str(row[8]) != binding.source_instance_id
                or str(row[9]) != binding.source_revision
                or str(row[10]) != binding.content_hash
                or str(row[11]) != receipt.workspace_id
                or str(row[12]) != receipt.task_id
                or str(row[13]) != _INTERNAL_PROJECTION_TOOL
                or str(row[14]) != "tool_execution"
                or context.get("knowledge_projection_admission")
                != expected_receipt
            ):
                return False
        return True


__all__ = ["InternalProjectionAdmissionStore"]
