"""
Meeting engine governance mixin.

Provides state snapshot capture, active intent tracking, and
intent patch approval gating for the meeting lifecycle.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import EventType

logger = logging.getLogger(__name__)


class MeetingGovernanceMixin:
    """Mixin providing governance methods for MeetingEngine."""

    def _capture_state_snapshot(self) -> Dict[str, Any]:
        """Capture a point-in-time state snapshot for before/after diff.

        Includes current intents, project state, and active meeting metadata.
        """
        snapshot: Dict[str, Any] = {
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
            "project_id": self.project_id,
            "lens_id": self.session.lens_id,
        }
        try:
            if self.project_id and self.profile_id:
                intents = self.store.list_intents(
                    self.profile_id, project_id=self.project_id
                )
                snapshot["intent_count"] = len(intents)
                snapshot["intents"] = [
                    {
                        "id": i.id,
                        "title": i.title,
                        "status": (
                            i.status.value
                            if hasattr(i.status, "value")
                            else str(i.status)
                        ),
                        "priority": (
                            i.priority.value
                            if hasattr(i.priority, "value")
                            else str(i.priority)
                        ),
                        "progress": i.progress_percentage,
                    }
                    for i in intents[:20]
                ]
        except Exception as exc:
            logger.warning("Failed to capture intent snapshot: %s", exc)
            snapshot["intents"] = []
            snapshot["intent_count"] = 0

        try:
            if self.project_id:
                project = self.store.get_project(self.project_id)
                if project:
                    snapshot["project_state"] = getattr(project, "state", None)
                    snapshot["project_title"] = getattr(project, "title", None)
        except Exception as exc:
            logger.warning("Failed to capture project snapshot: %s", exc)

        return snapshot

    def _get_active_intent_ids(self) -> List[str]:
        """Return IDs of active intents for this project (for turn trace)."""
        try:
            if self.project_id and self.profile_id:
                from backend.app.models.mindscape import IntentStatus

                intents = self.store.list_intents(
                    self.profile_id,
                    project_id=self.project_id,
                    status=IntentStatus.ACTIVE,
                )
                return [i.id for i in intents[:10]]
        except Exception as exc:
            logger.warning("Failed to fetch active intent IDs: %s", exc)
        return []

    def _check_intent_patch_approval(
        self,
        intent_id: str,
        patch_fields: Dict[str, Any],
        auto_approve_fields: Optional[List[str]] = None,
    ) -> bool:
        """Gate for intent mutations during meetings.

        Auto-approves low-risk field updates (progress_percentage, tags).
        Blocks high-risk mutations (status changes, priority overrides)
        by returning False and emitting a DECISION_PROPOSAL for human review.

        Args:
            intent_id: The intent being patched.
            patch_fields: Dict of field_name -> new_value.
            auto_approve_fields: Fields that can be auto-approved.
                Defaults to ["progress_percentage", "tags", "metadata"].

        Returns:
            True if the patch can proceed without human approval.
        """
        if auto_approve_fields is None:
            auto_approve_fields = ["progress_percentage", "tags", "metadata"]

        high_risk_fields = set(patch_fields.keys()) - set(auto_approve_fields)
        if not high_risk_fields:
            return True

        self._emit_event(
            EventType.DECISION_PROPOSAL,
            payload={
                "meeting_session_id": self.session.id,
                "type": "intent_patch_approval",
                "intent_id": intent_id,
                "patch_fields": patch_fields,
                "high_risk_fields": list(high_risk_fields),
                "auto_approved_fields": [
                    f for f in patch_fields if f in auto_approve_fields
                ],
                "requires_human_approval": True,
            },
        )
        logger.info(
            "Intent patch for %s blocked for human approval: high-risk fields %s",
            intent_id,
            high_risk_fields,
        )
        return False

    async def _try_coverage_audit(self, planner_content: str, round_num: int) -> None:
        """G2: Attempt to run CoverageAuditor on planner output.

        Best-effort: if the planner produces structured JSON with
        workstream references, run the auditor.  If parsing fails or
        no RequestContract exists, this is a graceful no-op.
        """
        if not self._request_contract:
            return

        import json

        from backend.app.services.orchestration.meeting.coverage_auditor import (
            CoverageAuditor,
            ProgramDraft,
        )

        # Try to extract JSON from planner output
        draft = None
        stripped = planner_content.strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(stripped[start : end + 1])
                if "workstreams" in data:
                    draft = ProgramDraft.model_validate(data)
            except (json.JSONDecodeError, Exception):
                pass

        if not draft:
            return  # Planner output is not structured — skip audit

        try:
            auditor = CoverageAuditor()
            matrix = auditor.audit(self._request_contract, draft)

            # Store coverage result on session metadata
            if self.session.metadata is None:
                self.session.metadata = {}
            self.session.metadata["last_coverage_matrix"] = matrix.model_dump()

            # Propagate coverage_pass to the verdict so _is_converged can gate
            if hasattr(self, "_last_round_verdict") and self._last_round_verdict:
                self._last_round_verdict.coverage_pass = matrix.coverage_pass

            logger.info(
                "CoverageAuditor round=%d: pass=%s pct=%.0f%% gaps=%s",
                round_num,
                matrix.coverage_pass,
                matrix.coverage_pct * 100,
                matrix.gap_summary(),
            )
        except Exception as exc:
            logger.warning(
                "CoverageAuditor failed (non-fatal, round=%d): %s",
                round_num,
                exc,
            )
