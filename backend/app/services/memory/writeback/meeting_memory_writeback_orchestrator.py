"""Meeting close writeback orchestration for canonical memory rollout."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.models.memory_contract import (
    MemoryEvidenceLink,
    MemoryItem,
    MemoryKind,
    MemoryUpdateMode,
    MemoryVersion,
)
from backend.app.models.personal_governance.session_digest import SessionDigest
from backend.app.services.memory.writeback.legacy_governance_projection_adapter import (
    LegacyGovernanceProjectionAdapter,
)
from backend.app.services.memory.writeback.legacy_metadata_memory_projection_adapter import (
    LegacyMetadataMemoryProjectionAdapter,
)
from backend.app.services.memory.writeback.evidence_collectors import (
    EvidenceCollectorRegistry,
    ExecutionTraceEvidenceCollector,
    GovernanceDecisionEvidenceCollector,
    IntentLogEvidenceCollector,
    LensPatchEvidenceCollector,
    StageResultEvidenceCollector,
)
from backend.app.services.memory.writeback.evidence_collectors.base import (
    merge_collection_summaries,
)
from backend.app.services.stores.postgres.memory_evidence_link_store import (
    MemoryEvidenceLinkStore,
)
from backend.app.services.stores.postgres.memory_item_store import MemoryItemStore
from backend.app.services.stores.postgres.memory_version_store import MemoryVersionStore
from backend.app.services.stores.postgres.memory_writeback_run_store import (
    MemoryWritebackRunStore,
)
from backend.app.services.stores.postgres.writeback_receipt_store import (
    WritebackReceiptStore,
)
from backend.app.services.lens.lens_receipt_store import LensReceiptStore
from backend.app.services.stores.lens_patch_store import LensPatchStore
from backend.app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
from backend.app.services.governance.governance_store import GovernanceStore
from backend.app.services.stores.postgres.intent_logs_store import (
    PostgresIntentLogsStore,
)
from backend.app.services.stores.stage_results_store import StageResultsStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.postgres.session_digest_store import SessionDigestStore
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.reasoning_traces_store import ReasoningTracesStore

logger = logging.getLogger(__name__)


class MeetingMemoryWritebackOrchestrator:
    """Drive meeting-close canonical writeback while preserving legacy extraction."""

    def __init__(
        self,
        *,
        run_store: Optional[MemoryWritebackRunStore] = None,
        digest_store: Optional[SessionDigestStore] = None,
        memory_item_store: Optional[MemoryItemStore] = None,
        memory_version_store: Optional[MemoryVersionStore] = None,
        evidence_link_store: Optional[MemoryEvidenceLinkStore] = None,
        meeting_session_store: Optional[MeetingSessionStore] = None,
        reasoning_trace_store: Optional[ReasoningTracesStore] = None,
        writeback_receipt_store: Optional[WritebackReceiptStore] = None,
        lens_receipt_store: Optional[LensReceiptStore] = None,
        lens_patch_store: Optional[LensPatchStore] = None,
        task_store: Optional[TasksStore] = None,
        artifact_store: Optional[PostgresArtifactsStore] = None,
        stage_results_store: Optional[StageResultsStore] = None,
        intent_log_store: Optional[PostgresIntentLogsStore] = None,
        governance_store: Optional[GovernanceStore] = None,
        legacy_projection_adapter: Optional[LegacyGovernanceProjectionAdapter] = None,
        metadata_projection_adapter: Optional[
            LegacyMetadataMemoryProjectionAdapter
        ] = None,
        stage_result_collector: Optional[StageResultEvidenceCollector] = None,
        intent_log_collector: Optional[IntentLogEvidenceCollector] = None,
        governance_decision_collector: Optional[
            GovernanceDecisionEvidenceCollector
        ] = None,
        lens_patch_collector: Optional[LensPatchEvidenceCollector] = None,
        execution_trace_collector: Optional[ExecutionTraceEvidenceCollector] = None,
    ) -> None:
        self.run_store = run_store or MemoryWritebackRunStore()
        self.digest_store = digest_store or SessionDigestStore()
        self.memory_item_store = memory_item_store or MemoryItemStore()
        self.memory_version_store = memory_version_store or MemoryVersionStore()
        self.evidence_link_store = evidence_link_store or MemoryEvidenceLinkStore()
        self.meeting_session_store = meeting_session_store or MeetingSessionStore()
        self.reasoning_trace_store = reasoning_trace_store or ReasoningTracesStore()
        self.writeback_receipt_store = writeback_receipt_store or WritebackReceiptStore()
        self.lens_receipt_store = lens_receipt_store or LensReceiptStore()
        self.lens_patch_store = lens_patch_store or LensPatchStore()
        self.task_store = task_store or TasksStore()
        self.artifact_store = artifact_store or PostgresArtifactsStore()
        self.stage_results_store = stage_results_store or StageResultsStore()
        self.intent_log_store = intent_log_store or PostgresIntentLogsStore()
        self.governance_store = governance_store or GovernanceStore()
        self.legacy_projection_adapter = (
            legacy_projection_adapter or LegacyGovernanceProjectionAdapter()
        )
        self.metadata_projection_adapter = (
            metadata_projection_adapter or LegacyMetadataMemoryProjectionAdapter()
        )
        self.phase2_collector_registry = EvidenceCollectorRegistry(
            [
                stage_result_collector
                or StageResultEvidenceCollector(
                    evidence_link_store=self.evidence_link_store,
                    meeting_session_store=self.meeting_session_store,
                    stage_results_store=self.stage_results_store,
                ),
                execution_trace_collector
                or ExecutionTraceEvidenceCollector(
                    evidence_link_store=self.evidence_link_store,
                    meeting_session_store=self.meeting_session_store,
                    task_store=self.task_store,
                ),
                intent_log_collector
                or IntentLogEvidenceCollector(
                    evidence_link_store=self.evidence_link_store,
                    intent_log_store=self.intent_log_store,
                ),
                governance_decision_collector
                or GovernanceDecisionEvidenceCollector(
                    evidence_link_store=self.evidence_link_store,
                    meeting_session_store=self.meeting_session_store,
                    governance_store=self.governance_store,
                ),
                lens_patch_collector
                or LensPatchEvidenceCollector(
                    evidence_link_store=self.evidence_link_store,
                    lens_patch_store=self.lens_patch_store,
                ),
            ]
        )

    def run_for_closed_session(
        self,
        *,
        session: Any,
        workspace: Any,
        profile_id: str,
    ) -> Dict[str, Any]:
        session_id = getattr(session, "id", "")
        idempotency_key = f"meeting_close:{session_id}"
        run, created = self.run_store.get_or_create(
            run_type="meeting_close",
            source_scope="meeting",
            source_id=session_id,
            idempotency_key=idempotency_key,
            metadata={
                "workspace_id": getattr(session, "workspace_id", ""),
                "project_id": getattr(session, "project_id", ""),
                "profile_id": profile_id,
            },
        )

        if not created and run.status == "completed":
            digest = self.digest_store.get_by_source("meeting", session_id)
            item = self.memory_item_store.find_by_subject(
                kind=MemoryKind.SESSION_EPISODE.value,
                subject_type="meeting_session",
                subject_id=session_id,
                context_type="workspace",
                context_id=getattr(session, "workspace_id", ""),
            )
            return {
                "run": run,
                "created": False,
                "digest": digest,
                "memory_item": item,
                "legacy_extraction_triggered": bool(
                    (run.summary or {}).get("legacy_extraction_triggered")
                ),
            }

        try:
            self.run_store.mark_stage(
                run.id,
                last_stage="digest",
                summary_update={"meeting_session_id": session_id},
            )
            digest = self.digest_store.get_by_source("meeting", session_id)
            digest_created = False
            if not digest:
                digest = SessionDigest.from_meeting_session(
                    session=session,
                    workspace=workspace,
                    profile_id=profile_id,
                )
                self.digest_store.create(digest)
                digest_created = True

            self.run_store.mark_stage(
                run.id,
                last_stage="canonical_item",
                summary_update={
                    "digest_id": digest.id,
                    "digest_created": digest_created,
                },
            )

            item = self.memory_item_store.find_by_subject(
                kind=MemoryKind.SESSION_EPISODE.value,
                subject_type="meeting_session",
                subject_id=session_id,
                context_type="workspace",
                context_id=getattr(session, "workspace_id", ""),
            )
            item_created = False
            if not item:
                item = MemoryItem.from_session_digest(digest, run_id=run.id)
                self.memory_item_store.create(item)
                self.memory_version_store.create(MemoryVersion.initial_from_item(item))
                item_created = True

            evidence_created = False
            if not self.evidence_link_store.exists(
                memory_item_id=item.id,
                evidence_type="session_digest",
                evidence_id=digest.id,
                link_role="derived_from",
            ):
                link = MemoryEvidenceLink.from_session_digest(item.id, digest)
                self.evidence_link_store.create(link)
                evidence_created = True

            (
                reasoning_trace_count,
                reasoning_trace_links_created,
                reasoning_trace_error,
            ) = self._safe_attach_reasoning_trace_evidence(
                memory_item_id=item.id,
                session_id=session_id,
            )
            (
                lens_receipt_count,
                lens_receipt_links_created,
                lens_receipt_error,
            ) = self._safe_attach_lens_receipt_evidence(
                memory_item_id=item.id,
                session_id=session_id,
            )
            (
                meeting_decision_count,
                meeting_decision_links_created,
                meeting_decision_error,
            ) = self._safe_attach_meeting_decision_evidence(
                memory_item_id=item.id,
                session_id=session_id,
            )
            (
                task_execution_count,
                task_execution_links_created,
                task_execution_error,
            ) = self._safe_attach_task_execution_evidence(
                memory_item_id=item.id,
                session_id=session_id,
            )
            (
                artifact_result_count,
                artifact_result_links_created,
                artifact_result_error,
            ) = self._safe_attach_artifact_result_evidence(
                memory_item_id=item.id,
                session_id=session_id,
            )
            phase2_evidence_summary = self._collect_phase2_evidence(
                memory_item_id=item.id,
                session=session,
            )

            self.run_store.mark_stage(
                run.id,
                last_stage="legacy_projection",
                summary_update={
                    "memory_item_id": item.id,
                    "memory_item_created": item_created,
                    "evidence_link_created": evidence_created,
                    "reasoning_trace_count": reasoning_trace_count,
                    "reasoning_trace_links_created": reasoning_trace_links_created,
                    "reasoning_trace_error": reasoning_trace_error,
                    "lens_receipt_count": lens_receipt_count,
                    "lens_receipt_links_created": lens_receipt_links_created,
                    "lens_receipt_error": lens_receipt_error,
                    "meeting_decision_count": meeting_decision_count,
                    "meeting_decision_links_created": meeting_decision_links_created,
                    "meeting_decision_error": meeting_decision_error,
                    "task_execution_count": task_execution_count,
                    "task_execution_links_created": task_execution_links_created,
                    "task_execution_error": task_execution_error,
                    "artifact_result_count": artifact_result_count,
                    "artifact_result_links_created": artifact_result_links_created,
                    "artifact_result_error": artifact_result_error,
                    **phase2_evidence_summary,
                },
            )

            legacy_triggered, legacy_error = self._safe_dispatch_legacy_projection(
                digest,
                session_id,
                source_memory_item_id=item.id,
                source_writeback_run_id=run.id,
            )
            metadata_triggered, metadata_error = (
                self._safe_dispatch_metadata_projection(
                    digest,
                    session_id,
                    source_memory_item_id=item.id,
                    source_writeback_run_id=run.id,
                )
            )
            (
                writeback_receipt_count,
                writeback_receipt_links_created,
                writeback_receipt_error,
            ) = self._safe_attach_writeback_receipt_evidence(memory_item_id=item.id)

            completed_run = self.run_store.mark_completed(
                run.id,
                summary={
                    "digest_id": digest.id,
                    "memory_item_id": item.id,
                    "legacy_extraction_triggered": legacy_triggered,
                    "legacy_extraction_error": legacy_error,
                    "legacy_metadata_projection_triggered": metadata_triggered,
                    "legacy_metadata_projection_error": metadata_error,
                    "reasoning_trace_count": reasoning_trace_count,
                    "reasoning_trace_links_created": reasoning_trace_links_created,
                    "reasoning_trace_error": reasoning_trace_error,
                    "lens_receipt_count": lens_receipt_count,
                    "lens_receipt_links_created": lens_receipt_links_created,
                    "lens_receipt_error": lens_receipt_error,
                    "meeting_decision_count": meeting_decision_count,
                    "meeting_decision_links_created": meeting_decision_links_created,
                    "meeting_decision_error": meeting_decision_error,
                    "task_execution_count": task_execution_count,
                    "task_execution_links_created": task_execution_links_created,
                    "task_execution_error": task_execution_error,
                    "artifact_result_count": artifact_result_count,
                    "artifact_result_links_created": artifact_result_links_created,
                    "artifact_result_error": artifact_result_error,
                    "writeback_receipt_count": writeback_receipt_count,
                    "writeback_receipt_links_created": writeback_receipt_links_created,
                    "writeback_receipt_error": writeback_receipt_error,
                    **phase2_evidence_summary,
                },
                update_mode_summary={MemoryUpdateMode.APPEND.value: 1},
                last_stage="completed",
            )

            logger.info(
                "Meeting memory writeback completed for session %s (run=%s item=%s)",
                session_id,
                run.id,
                item.id,
            )
            return {
                "run": completed_run or run,
                "created": created,
                "digest": digest,
                "memory_item": item,
                "legacy_extraction_triggered": legacy_triggered,
                "legacy_metadata_projection_triggered": metadata_triggered,
            }
        except Exception as exc:
            self.run_store.mark_failed(
                run.id,
                error_detail=str(exc),
                summary={"meeting_session_id": session_id},
                last_stage="failed",
            )
            raise

    def _safe_dispatch_legacy_projection(
        self,
        digest: SessionDigest,
        session_id: str,
        *,
        source_memory_item_id: str,
        source_writeback_run_id: str,
    ) -> tuple[bool, Optional[str]]:
        try:
            self.legacy_projection_adapter.dispatch_digest_projection(
                digest,
                session_id,
                source_memory_item_id=source_memory_item_id,
                source_writeback_run_id=source_writeback_run_id,
            )
            return True, None
        except Exception as exc:
            logger.warning(
                "Legacy extraction dispatch failed for %s: %s",
                session_id,
                exc,
            )
            return False, str(exc)

    def _collect_phase2_evidence(
        self,
        *,
        memory_item_id: str,
        session: Any,
    ) -> Dict[str, Any]:
        results = self.phase2_collector_registry.collect(
            memory_item_id=memory_item_id,
            session=session,
        )
        return merge_collection_summaries(results)

    def _safe_attach_reasoning_trace_evidence(
        self,
        *,
        memory_item_id: str,
        session_id: str,
    ) -> tuple[int, int, Optional[str]]:
        try:
            traces = self.reasoning_trace_store.get_by_session(session_id)
            created_count = 0
            for trace in traces:
                if self.evidence_link_store.exists(
                    memory_item_id=memory_item_id,
                    evidence_type="reasoning_trace",
                    evidence_id=trace.id,
                    link_role="supports",
                ):
                    continue
                self.evidence_link_store.create(
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

    def _safe_attach_lens_receipt_evidence(
        self,
        *,
        memory_item_id: str,
        session_id: str,
    ) -> tuple[int, int, Optional[str]]:
        try:
            traces = self.reasoning_trace_store.get_by_session(session_id)
            receipts = []
            seen_receipt_ids = set()
            for trace in traces:
                if not trace.execution_id:
                    continue
                receipt = self.lens_receipt_store.get_by_execution_id(trace.execution_id)
                if receipt is None or receipt.id in seen_receipt_ids:
                    continue
                seen_receipt_ids.add(receipt.id)
                receipts.append(receipt)

            created_count = 0
            for receipt in receipts:
                if self.evidence_link_store.exists(
                    memory_item_id=memory_item_id,
                    evidence_type="lens_receipt",
                    evidence_id=receipt.id,
                    link_role="supports",
                ):
                    continue
                self.evidence_link_store.create(
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

    def _safe_attach_writeback_receipt_evidence(
        self,
        *,
        memory_item_id: str,
    ) -> tuple[int, int, Optional[str]]:
        try:
            receipts = self.writeback_receipt_store.list_by_canonical_memory_item(
                memory_item_id
            )
            created_count = 0
            for receipt in receipts:
                if self.evidence_link_store.exists(
                    memory_item_id=memory_item_id,
                    evidence_type="writeback_receipt",
                    evidence_id=receipt.id,
                    link_role="derived_from",
                ):
                    continue
                self.evidence_link_store.create(
                    MemoryEvidenceLink.from_writeback_receipt(
                        memory_item_id,
                        receipt,
                    )
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

    def _safe_attach_task_execution_evidence(
        self,
        *,
        memory_item_id: str,
        session_id: str,
    ) -> tuple[int, int, Optional[str]]:
        try:
            decisions = self.meeting_session_store.list_decisions_by_session(session_id)
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

            found_count = 0
            created_count = 0
            for execution_id in execution_ids:
                task = self.task_store.get_task_by_execution_id(execution_id)
                if task is None:
                    continue
                found_count += 1
                evidence_id = task.execution_id or task.id
                if self.evidence_link_store.exists(
                    memory_item_id=memory_item_id,
                    evidence_type="task_execution",
                    evidence_id=evidence_id,
                    link_role="supports",
                ):
                    continue
                self.evidence_link_store.create(
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

    def _safe_attach_artifact_result_evidence(
        self,
        *,
        memory_item_id: str,
        session_id: str,
    ) -> tuple[int, int, Optional[str]]:
        try:
            decisions = self.meeting_session_store.list_decisions_by_session(session_id)
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

            found_count = 0
            created_count = 0
            for execution_id in execution_ids:
                artifact = self.artifact_store.get_by_execution_id(execution_id)
                if artifact is None:
                    continue
                found_count += 1
                if self.evidence_link_store.exists(
                    memory_item_id=memory_item_id,
                    evidence_type="artifact_result",
                    evidence_id=artifact.id,
                    link_role="supports",
                ):
                    continue
                self.evidence_link_store.create(
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

    def _safe_attach_meeting_decision_evidence(
        self,
        *,
        memory_item_id: str,
        session_id: str,
    ) -> tuple[int, int, Optional[str]]:
        try:
            decisions = self.meeting_session_store.list_decisions_by_session(session_id)
            created_count = 0
            for decision in decisions:
                if self.evidence_link_store.exists(
                    memory_item_id=memory_item_id,
                    evidence_type="meeting_decision",
                    evidence_id=decision.id,
                    link_role="supports",
                ):
                    continue
                self.evidence_link_store.create(
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

    def _safe_dispatch_metadata_projection(
        self,
        digest: SessionDigest,
        session_id: str,
        *,
        source_memory_item_id: str,
        source_writeback_run_id: str,
    ) -> tuple[bool, Optional[str]]:
        try:
            self.metadata_projection_adapter.dispatch_digest_projection(
                digest,
                source_memory_item_id=source_memory_item_id,
                source_writeback_run_id=source_writeback_run_id,
            )
            return True, None
        except Exception as exc:
            logger.warning(
                "Legacy metadata projection failed for %s: %s",
                session_id,
                exc,
            )
            return False, str(exc)
