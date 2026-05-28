"""Meeting session start and close lifecycle helpers."""

import logging
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_session import MeetingStatus
from backend.app.models.mindscape import EventType

logger = logging.getLogger(__name__)


class MeetingSessionLifecycleMixin:
    @staticmethod
    def _resolve_locale(workspace) -> str:
        """Resolve locale from workspace, settings, or default fallback."""
        ws_locale = getattr(workspace, "default_locale", None)
        if ws_locale:
            return ws_locale

        try:
            from backend.app.services.system_settings_store import SystemSettingsStore

            store = SystemSettingsStore()
            setting = store.get_setting("default_language")
            if setting and setting.value:
                return str(setting.value)
        except Exception:
            pass

        return "zh-TW"

    def _start_session(self) -> None:
        """Transition session to ACTIVE and capture initial state snapshot."""
        self.session.start()
        self.session.status = MeetingStatus.ACTIVE
        self.session.state_before = self._capture_state_snapshot()

        ctx = getattr(self, "ctx", None)
        if ctx and hasattr(ctx, "model_dump"):
            self.session.metadata["execution_context_snapshot"] = {
                "executor_runtime_id": ctx.executor_runtime_id,
                "auth_type": ctx.auth_type,
                "auth_status": ctx.auth_status,
                "max_iterations": ctx.max_iterations,
                "route_kind": ctx.route_kind,
                "execution_profile": ctx.execution_profile,
            }

        workflow_evidence_diagnostics = getattr(
            self,
            "_workflow_evidence_diagnostics",
            None,
        )
        if isinstance(workflow_evidence_diagnostics, dict):
            self.session.metadata["workflow_evidence_diagnostics"] = (
                workflow_evidence_diagnostics
            )

        selected_memory_packet_trace = self._capture_selected_memory_packet_trace()
        if isinstance(selected_memory_packet_trace, dict):
            self.session.metadata["selected_memory_packet"] = (
                selected_memory_packet_trace.get("selected_memory_packet") or {}
            )
            self.session.metadata["selected_memory_packet_node_ids"] = list(
                selected_memory_packet_trace.get("selected_memory_packet_node_ids") or []
            )

        self.session_store.update(self.session)
        self._emit_event(
            EventType.MEETING_START,
            payload={
                "meeting_session_id": self.session.id,
                "meeting_type": self.session.meeting_type,
                "agenda": self.session.agenda,
                "lens_id": self.session.lens_id,
                "workflow_evidence_profile": (
                    workflow_evidence_diagnostics.get("profile")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_scope": (
                    workflow_evidence_diagnostics.get("scope")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_selected_line_count": (
                    workflow_evidence_diagnostics.get("selected_line_count")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_total_line_budget": (
                    workflow_evidence_diagnostics.get("total_line_budget")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_total_candidate_count": (
                    workflow_evidence_diagnostics.get("total_candidate_count")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_total_dropped_count": (
                    workflow_evidence_diagnostics.get("total_dropped_count")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_rendered_section_count": (
                    workflow_evidence_diagnostics.get("rendered_section_count")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
                "workflow_evidence_budget_utilization_ratio": (
                    workflow_evidence_diagnostics.get("budget_utilization_ratio")
                    if isinstance(workflow_evidence_diagnostics, dict)
                    else None
                ),
            },
        )

    def _close_session(
        self,
        minutes_md: str,
        action_items: List[Dict[str, Any]],
        dispatch_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Close the session with final state snapshot and minutes."""
        self.session.begin_closing()
        self.session.minutes_md = minutes_md
        self.session.action_items = action_items
        self.session.state_after = self._capture_state_snapshot()
        self.session.status = MeetingStatus.CLOSED
        self.session.close()
        self.session_store.update(self.session)

        decisions = []
        try:
            from backend.app.models.meeting_decision import MeetingDecision

            decisions = MeetingDecision.extract_from_session(self.session)
            if decisions:
                self.session_store.save_decisions(decisions)
                logger.info(
                    "Persisted %d decisions for session %s",
                    len(decisions),
                    self.session.id,
                )
        except Exception as exc:
            logger.warning(
                "Failed to persist meeting decisions for %s: %s",
                self.session.id,
                exc,
            )

        selected_packet_node_ids = list(
            self.session.metadata.get("selected_memory_packet_node_ids") or []
        )
        if not selected_packet_node_ids:
            selected_memory_packet_trace = self._capture_selected_memory_packet_trace()
            if isinstance(selected_memory_packet_trace, dict):
                self.session.metadata["selected_memory_packet"] = (
                    selected_memory_packet_trace.get("selected_memory_packet") or {}
                )
                selected_packet_node_ids = list(
                    selected_memory_packet_trace.get("selected_memory_packet_node_ids")
                    or []
                )
                self.session.metadata["selected_memory_packet_node_ids"] = (
                    selected_packet_node_ids
                )

        canonical_memory = None
        try:
            from backend.app.services.memory.writeback.meeting_memory_writeback_orchestrator import (
                MeetingMemoryWritebackOrchestrator,
            )

            orchestrator = MeetingMemoryWritebackOrchestrator()
            writeback_result = orchestrator.run_for_closed_session(
                session=self.session,
                workspace=getattr(self, "workspace", None),
                profile_id=getattr(self, "profile_id", ""),
            )

            digest = writeback_result.get("digest")
            memory_item = writeback_result.get("memory_item")
            run = writeback_result.get("run")
            if digest and memory_item and run:
                canonical_memory = {
                    "memory_item_id": getattr(memory_item, "id", ""),
                    "digest_id": getattr(digest, "id", ""),
                    "writeback_run_id": getattr(run, "id", ""),
                    "lifecycle_status": getattr(memory_item, "lifecycle_status", ""),
                    "verification_status": getattr(
                        memory_item,
                        "verification_status",
                        "",
                    ),
                }
                self.session.metadata["canonical_memory_item_id"] = memory_item.id
                self.session.metadata["canonical_memory"] = canonical_memory
                self.session_store.update(self.session)
                self._emit_event(
                    EventType.MEMORY_WRITEBACK,
                    payload={
                        "meeting_session_id": self.session.id,
                        "project_id": self.session.project_id,
                        **canonical_memory,
                    },
                    entity_ids=[memory_item.id],
                    metadata={
                        "project_id": self.session.project_id,
                        "memory_item_id": memory_item.id,
                        "digest_id": digest.id,
                        "writeback_run_id": run.id,
                    },
                )
            logger.info(
                "Meeting writeback run %s emitted digest %s and memory item %s for session %s",
                getattr(run, "id", "unknown"),
                getattr(digest, "id", "unknown"),
                getattr(memory_item, "id", "unknown"),
                self.session.id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to execute meeting memory writeback for %s: %s",
                self.session.id,
                exc,
            )

        self.session.metadata["memory_impact_trace"] = self._build_memory_impact_trace(
            selected_packet_node_ids=selected_packet_node_ids,
            canonical_memory=canonical_memory,
            meeting_decision_ids=[
                getattr(decision, "id", "")
                for decision in decisions
                if getattr(decision, "id", "")
            ],
            action_items=action_items,
        )
        self._writeback_capability_metadata_updates_to_workspace()
        self.session_store.update(self.session)

        self._emit_event(
            EventType.MEETING_END,
            payload={
                "meeting_session_id": self.session.id,
                "round_count": self.session.round_count,
                "action_item_count": len(action_items),
                "state_diff": self.session.state_diff,
                "dispatch_result": dispatch_result,
                "canonical_memory": canonical_memory,
            },
        )
