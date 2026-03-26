"""ExecutionTrace collector for governed-memory evidence expansion."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from backend.app.models.memory_contract import MemoryEvidenceLink
from backend.app.services.memory.writeback.evidence_collectors.base import (
    EvidenceCollectionResult,
    collect_unique_execution_ids,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.postgres.memory_evidence_link_store import (
    MemoryEvidenceLinkStore,
)

logger = logging.getLogger(__name__)


class ExecutionTraceEvidenceCollector:
    """Attach runtime trace summaries from task results as execution evidence."""

    summary_key = "execution_trace"

    def __init__(
        self,
        *,
        evidence_link_store: MemoryEvidenceLinkStore,
        meeting_session_store: Optional[MeetingSessionStore] = None,
        task_store: Optional[TasksStore] = None,
    ) -> None:
        self.evidence_link_store = evidence_link_store
        self.meeting_session_store = meeting_session_store or MeetingSessionStore()
        self.task_store = task_store or TasksStore()

    def collect(
        self,
        *,
        memory_item_id: str,
        session: Any,
    ) -> EvidenceCollectionResult:
        session_id = getattr(session, "id", "")
        try:
            decisions = self.meeting_session_store.list_decisions_by_session(session_id)
            execution_ids = collect_unique_execution_ids(decisions)

            found_count = 0
            created_count = 0
            for execution_id in execution_ids:
                task = self.task_store.get_task_by_execution_id(execution_id)
                trace_payload = self._extract_trace_payload(task)
                if trace_payload is None:
                    continue
                found_count += 1
                evidence_id = str(
                    trace_payload.get("execution_id")
                    or trace_payload.get("trace_id")
                    or execution_id
                )
                if self.evidence_link_store.exists(
                    memory_item_id=memory_item_id,
                    evidence_type="execution_trace",
                    evidence_id=evidence_id,
                    link_role="supports",
                ):
                    continue
                self.evidence_link_store.create(
                    MemoryEvidenceLink.from_execution_trace(
                        memory_item_id,
                        trace_payload,
                        task=task,
                    )
                )
                created_count += 1

            return EvidenceCollectionResult(
                summary_key=self.summary_key,
                found_count=found_count,
                created_count=created_count,
            )
        except Exception as exc:
            logger.warning(
                "Execution trace evidence attachment failed for %s: %s",
                session_id,
                exc,
            )
            return EvidenceCollectionResult(
                summary_key=self.summary_key,
                error=str(exc),
            )

    def _extract_trace_payload(self, task: Any) -> Optional[dict[str, Any]]:
        if task is None or not isinstance(getattr(task, "result", None), dict):
            return None
        trace_payload = task.result.get("execution_trace")
        if not isinstance(trace_payload, dict):
            return None
        if not any(
            trace_payload.get(key)
            for key in (
                "execution_id",
                "trace_id",
                "agent",
                "tool_calls",
                "files_created",
                "files_modified",
                "sandbox_path",
            )
        ):
            return None
        return self._enrich_trace_payload(trace_payload)

    def _enrich_trace_payload(self, trace_payload: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(trace_payload)
        trace_file_result = self._load_trace_payload_from_file(trace_payload)
        if trace_file_result is not None:
            trace_file_payload, trace_file_path = trace_file_result
            for key, value in trace_file_payload.items():
                if value is not None:
                    enriched[key] = value
            enriched["trace_source"] = "trace_file"
            enriched["trace_file_path"] = trace_file_path
        else:
            enriched["trace_source"] = "summary_payload"
        return enriched

    def _load_trace_payload_from_file(
        self,
        trace_payload: dict[str, Any],
    ) -> Optional[tuple[dict[str, Any], str]]:
        sandbox_path = trace_payload.get("sandbox_path")
        if not isinstance(sandbox_path, str) or not sandbox_path.strip():
            return None
        base_path = Path(sandbox_path.strip())
        candidate_ids = []
        for key in ("execution_id", "trace_id"):
            value = trace_payload.get(key)
            if isinstance(value, str) and value.strip() and value.strip() not in candidate_ids:
                candidate_ids.append(value.strip())

        trace_dir = base_path / ".mindscape" / "traces"
        for candidate_id in candidate_ids:
            trace_file = trace_dir / f"{candidate_id}.json"
            if not trace_file.exists():
                continue
            try:
                return json.loads(trace_file.read_text()), str(trace_file)
            except Exception as exc:
                logger.warning(
                    "Execution trace file load failed for %s: %s",
                    trace_file,
                    exc,
                )
                return None
        return None
