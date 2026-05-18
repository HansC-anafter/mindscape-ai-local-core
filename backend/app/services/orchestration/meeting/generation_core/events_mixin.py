"""Meeting generation event helpers."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MeetingGenerationEventsMixin:
    async def _emit_clarification_event(self, questions: list[str]) -> None:
        """Emit a decision_required event so the UI shows a confirmation card."""
        try:
            import uuid
            from datetime import datetime, timezone
            from backend.app.models.mindscape import MindEvent, EventType, EventActor

            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                actor=EventActor.AGENT,
                channel="meeting",
                profile_id=getattr(self, "profile_id", "") or "",
                project_id=getattr(self, "project_id", None),
                workspace_id=self.workspace.id,
                event_type=EventType.DECISION_REQUIRED,
                payload={
                    "card_type": "decision",
                    "priority": "high",
                    "requires_user_approval": True,
                    "clarification_questions": questions,
                    "selected_playbook_code": f"agent:{self.executor_runtime}",
                    "rationale": "Task risk assessment requires user confirmation before proceeding.",
                },
            )
            self.store.create_event(event)
            logger.info("Emitted DECISION_REQUIRED event for meeting clarification")
        except Exception as exc:
            logger.warning("Failed to emit clarification event: %s", exc)

    def _retry_delay_seconds(self, attempt: int) -> float:
        """Calculate retry delay based on strategy."""
        if self.retry_strategy == "immediate":
            return 0.0
        if self.retry_strategy == "exponential_backoff":
            return float(min(2**attempt, 8))
        return 0.0

    def _emit_runtime_unavailable_event(
        self,
        runtime_id: str,
        error: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """OP-6: Emit structured RuntimeUnavailableEvent for observability.

        Enables dashboards and alerting to track runtime failures without
        log parsing.  Fallback decisions happen ABOVE the meeting engine,
        per v3 constraint.
        """
        try:
            payload = {
                "runtime_id": runtime_id,
                "error": error[:500],
                "reason": reason,
                "session_id": getattr(getattr(self, "session", None), "id", None),
                "model_name": getattr(self, "model_name", None),
            }
            if metadata:
                payload.update(metadata)
            self._emit_event(
                "runtime_unavailable",
                payload=payload,
            )
        except Exception:
            pass
