"""Evidence link attachment helpers for meeting memory writeback."""

import logging
from typing import Optional

from backend.app.models.memory_contract import MemoryEvidenceLink

logger = logging.getLogger(__name__)


def _execution_ids_from_decisions(meeting_session_store, session_id: str) -> list[str]:
    decisions = meeting_session_store.list_decisions_by_session(session_id)
    execution_ids = []
    seen_execution_ids = set()
    for decision in decisions:
        source_action_item = decision.source_action_item or {}
        execution_id = source_action_item.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id.strip():
            continue
        execution_id = execution_id.strip()
        if execution_id in seen_execution_ids:
            continue
        seen_execution_ids.add(execution_id)
        execution_ids.append(execution_id)
    return execution_ids


def attach_reasoning_trace_evidence(
    *,
    evidence_link_store,
    reasoning_trace_store,
    memory_item_id: str,
    session_id: str,
) -> tuple[int, int, Optional[str]]:
    try:
        traces = reasoning_trace_store.get_by_session(session_id)
        created_count = 0
        for trace in traces:
            if evidence_link_store.exists(
                memory_item_id=memory_item_id,
                evidence_type="reasoning_trace",
                evidence_id=trace.id,
                link_role="supports",
            ):
                continue
            evidence_link_store.create(
                MemoryEvidenceLink.from_reasoning_trace(memory_item_id, trace)
            )
            created_count += 1
        return len(traces), created_count, None
    except Exception as exc:
        logger.warning(
            "Reasoning trace evidence attachment failed for %s: %s",
            session_id,
            exc,
        )
        return 0, 0, str(exc)


def attach_lens_receipt_evidence(
    *,
    evidence_link_store,
    reasoning_trace_store,
    lens_receipt_store,
    memory_item_id: str,
    session_id: str,
) -> tuple[int, int, Optional[str]]:
    try:
        traces = reasoning_trace_store.get_by_session(session_id)
        receipts = []
        seen_receipt_ids = set()
        for trace in traces:
            if not trace.execution_id:
                continue
            receipt = lens_receipt_store.get_by_execution_id(trace.execution_id)
            if receipt is None or receipt.id in seen_receipt_ids:
                continue
            seen_receipt_ids.add(receipt.id)
            receipts.append(receipt)

        created_count = 0
        for receipt in receipts:
            if evidence_link_store.exists(
                memory_item_id=memory_item_id,
                evidence_type="lens_receipt",
                evidence_id=receipt.id,
                link_role="supports",
            ):
                continue
            evidence_link_store.create(
                MemoryEvidenceLink.from_lens_receipt(memory_item_id, receipt)
            )
            created_count += 1
        return len(receipts), created_count, None
    except Exception as exc:
        logger.warning(
            "Lens receipt evidence attachment failed for %s: %s",
            session_id,
            exc,
        )
        return 0, 0, str(exc)


def attach_writeback_receipt_evidence(
    *,
    evidence_link_store,
    writeback_receipt_store,
    memory_item_id: str,
) -> tuple[int, int, Optional[str]]:
    try:
        receipts = writeback_receipt_store.list_by_canonical_memory_item(
            memory_item_id
        )
        created_count = 0
        for receipt in receipts:
            if evidence_link_store.exists(
                memory_item_id=memory_item_id,
                evidence_type="writeback_receipt",
                evidence_id=receipt.id,
                link_role="derived_from",
            ):
                continue
            evidence_link_store.create(
                MemoryEvidenceLink.from_writeback_receipt(memory_item_id, receipt)
            )
            created_count += 1
        return len(receipts), created_count, None
    except Exception as exc:
        logger.warning(
            "Writeback receipt evidence attachment failed for %s: %s",
            memory_item_id,
            exc,
        )
        return 0, 0, str(exc)


def attach_task_execution_evidence(
    *,
    evidence_link_store,
    meeting_session_store,
    task_store,
    memory_item_id: str,
    session_id: str,
) -> tuple[int, int, Optional[str]]:
    try:
        execution_ids = _execution_ids_from_decisions(meeting_session_store, session_id)
        found_count = 0
        created_count = 0
        for execution_id in execution_ids:
            task = task_store.get_task_by_execution_id(execution_id)
            if task is None:
                continue
            found_count += 1
            evidence_id = task.execution_id or task.id
            if evidence_link_store.exists(
                memory_item_id=memory_item_id,
                evidence_type="task_execution",
                evidence_id=evidence_id,
                link_role="supports",
            ):
                continue
            evidence_link_store.create(
                MemoryEvidenceLink.from_task_execution(memory_item_id, task)
            )
            created_count += 1
        return found_count, created_count, None
    except Exception as exc:
        logger.warning(
            "Task execution evidence attachment failed for %s: %s",
            session_id,
            exc,
        )
        return 0, 0, str(exc)


def attach_artifact_result_evidence(
    *,
    evidence_link_store,
    meeting_session_store,
    artifact_store,
    memory_item_id: str,
    session_id: str,
) -> tuple[int, int, Optional[str]]:
    try:
        execution_ids = _execution_ids_from_decisions(meeting_session_store, session_id)
        found_count = 0
        created_count = 0
        for execution_id in execution_ids:
            artifact = artifact_store.get_by_execution_id(execution_id)
            if artifact is None:
                continue
            found_count += 1
            if evidence_link_store.exists(
                memory_item_id=memory_item_id,
                evidence_type="artifact_result",
                evidence_id=artifact.id,
                link_role="supports",
            ):
                continue
            evidence_link_store.create(
                MemoryEvidenceLink.from_artifact_result(memory_item_id, artifact)
            )
            created_count += 1
        return found_count, created_count, None
    except Exception as exc:
        logger.warning(
            "Artifact result evidence attachment failed for %s: %s",
            session_id,
            exc,
        )
        return 0, 0, str(exc)


def attach_meeting_decision_evidence(
    *,
    evidence_link_store,
    meeting_session_store,
    memory_item_id: str,
    session_id: str,
) -> tuple[int, int, Optional[str]]:
    try:
        decisions = meeting_session_store.list_decisions_by_session(session_id)
        created_count = 0
        for decision in decisions:
            if evidence_link_store.exists(
                memory_item_id=memory_item_id,
                evidence_type="meeting_decision",
                evidence_id=decision.id,
                link_role="supports",
            ):
                continue
            evidence_link_store.create(
                MemoryEvidenceLink.from_meeting_decision(memory_item_id, decision)
            )
            created_count += 1
        return len(decisions), created_count, None
    except Exception as exc:
        logger.warning(
            "Meeting decision evidence attachment failed for %s: %s",
            session_id,
            exc,
        )
        return 0, 0, str(exc)
