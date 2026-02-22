"""
Meeting engine prompt building mixin.

Handles turn prompt construction, locale resolution, project context
injection, history snippets, and convergence detection.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MeetingPromptsMixin:
    """Mixin providing prompt construction methods for MeetingEngine."""

    def _build_project_context(self) -> str:
        """Fetch project data and recent activity to provide meeting context."""
        if not self.project_id:
            return ""

        parts: List[str] = []
        try:
            project = self.store.get_project(self.project_id)
            if project:
                parts.append(f"Project: {getattr(project, 'title', self.project_id)}")
                ptype = getattr(project, "type", None)
                if ptype:
                    parts.append(f"Type: {ptype}")
                pstate = getattr(project, "state", None)
                if pstate:
                    parts.append(f"State: {pstate}")
                pmeta = getattr(project, "metadata", None)
                if pmeta and isinstance(pmeta, dict):
                    summary_keys = [
                        "goal",
                        "goals",
                        "description",
                        "brief",
                        "scope",
                        "deliverables",
                        "requirements",
                    ]
                    for key in summary_keys:
                        val = pmeta.get(key)
                        if val:
                            parts.append(f"{key.capitalize()}: {val}")
        except Exception as exc:
            logger.warning("Failed to fetch project for meeting context: %s", exc)

        try:
            recent_events = self.store.get_events_by_project(self.project_id, limit=10)
            if recent_events:
                activity_lines = []
                for ev in recent_events[:5]:
                    ev_type = getattr(ev, "event_type", "")
                    payload = getattr(ev, "payload", {}) or {}
                    summary = (
                        payload.get("message") or payload.get("title") or str(ev_type)
                    )
                    if len(summary) > 120:
                        summary = summary[:120] + "..."
                    activity_lines.append(f"  - {summary}")
                if activity_lines:
                    parts.append(
                        "Recent project activity:\n" + "\n".join(activity_lines)
                    )
        except Exception as exc:
            logger.warning("Failed to fetch project events for meeting: %s", exc)

        return "\n".join(parts) if parts else ""

    def _build_turn_prompt(
        self,
        agent_id: str,
        round_num: int,
        user_message: str,
        decision: Optional[str],
        planner_proposals: List[str],
        critic_notes: List[str],
    ) -> str:
        """Build the full prompt for a single agent turn."""
        history = self._history_snippet()
        agenda = self.session.agenda or [user_message]
        agenda_text = "\n".join([f"- {a}" for a in agenda])
        latest_proposal = planner_proposals[-1] if planner_proposals else "(none)"
        latest_critic = critic_notes[-1] if critic_notes else "(none)"

        locale_map = {
            "zh-TW": "Traditional Chinese (zh-TW)",
            "zh-CN": "Simplified Chinese (zh-CN)",
            "en": "English",
            "ja": "Japanese",
        }
        locale_label = locale_map.get(self._locale, self._locale)
        locale_directive = (
            f"IMPORTANT: All your responses MUST be in {locale_label}. "
            f"Do not mix languages.\n\n"
        )

        project_block = ""
        if self._project_context:
            project_block = (
                f"=== Project Context ===\n"
                f"{self._project_context}\n"
                f"=== End Project Context ===\n\n"
                f"This meeting is about the project above. "
                f"All discussion, proposals, and action items must be "
                f"relevant to this specific project.\n\n"
            )

        common = (
            locale_directive + project_block + f"Meeting session: {self.session.id}\n"
            f"Round: {round_num}/{max(1, self.session.max_rounds)}\n"
            f"Agenda:\n{agenda_text}\n\n"
            f"User request:\n{user_message}\n\n"
            f"Current decision draft:\n{decision or '(not finalized)'}\n\n"
            f"Latest planner proposal:\n{latest_proposal}\n\n"
            f"Latest critic note:\n{latest_critic}\n\n"
            f"Recent turns:\n{history}\n\n"
        )

        if agent_id == "facilitator":
            return (
                common
                + "As facilitator, synthesize progress and decide if another round is needed. "
                "If converged, include the marker [CONVERGED]. Keep concise."
            )
        if agent_id == "planner":
            return (
                common
                + "As planner, propose a concrete, executable plan with clear steps and ownership."
            )
        if agent_id == "critic":
            return (
                common
                + "As critic, challenge assumptions, identify risks, and suggest mitigations."
            )
        return (
            common + "As executor, produce only JSON array with up to 3 action items. "
            'Schema: [{"title":"...","description":"...","assigned_to":"executor",'
            '"priority":"low|medium|high","playbook_code":null}]'
        )

    def _history_snippet(self) -> str:
        """Return a concise summary of recent turn history."""
        if not self._turn_history:
            return "(none)"
        recent = self._turn_history[-6:]
        return "\n".join(
            [f"- R{t['round']} {t['role']}: {t['content'][:220]}" for t in recent]
        )

    def _fallback_turn_text(
        self, agent_id: str, round_num: int, user_message: str
    ) -> str:
        """Generate a deterministic fallback turn when LLM is unavailable."""
        if agent_id == "facilitator":
            return (
                f"Round {round_num} facilitation summary for '{user_message[:80]}'. "
                "Planner and critic inputs consolidated."
            )
        if agent_id == "planner":
            return f"Proposal R{round_num}: execute incrementally, track evidence, and verify outcomes."
        if agent_id == "critic":
            return f"Critique R{round_num}: verify data contract, add rollback checks, and test failure paths."
        return json.dumps(
            [
                {
                    "title": "Implement finalized decision",
                    "description": "Translate final meeting decision into executable work.",
                    "assigned_to": "executor",
                    "priority": "medium",
                    "playbook_code": None,
                }
            ]
        )

    def _is_converged(
        self, round_num: int, max_rounds: int, facilitator_text: str
    ) -> bool:
        """Check whether the meeting has converged."""
        if round_num >= max_rounds:
            return True
        if round_num >= 2 and "[converged]" in facilitator_text.lower():
            return True
        return False

    def _render_minutes(
        self,
        user_message: str,
        decision: str,
        critic_notes: List[str],
        action_items: List[Dict[str, Any]],
        converged: bool,
    ) -> str:
        """Render final meeting minutes as markdown."""
        status = "converged" if converged else "partial"
        action_lines = "\n".join(
            [
                (
                    f"| {idx} | {item.get('title', 'Action Item')} | "
                    f"{item.get('assigned_to', 'executor')} | {item.get('priority', 'medium')} |"
                )
                for idx, item in enumerate(action_items, start=1)
            ]
        )
        if not action_lines:
            action_lines = "| 1 | No action item generated | executor | medium |"
        risk_text = "\n".join([f"- {note}" for note in critic_notes]) or "- None"

        return (
            f"# Meeting Minutes — {self.session.id[:8]}\n"
            f"**Status**: {status}  \n"
            f"**Rounds**: {self.session.round_count}\n\n"
            f"## Agenda\n- {user_message}\n\n"
            f"## Decisions\n- {decision}\n\n"
            f"## Risks & Concerns\n{risk_text}\n\n"
            "## Action Items\n"
            "| # | Task | Assigned To | Priority |\n"
            "|---|------|-------------|----------|\n"
            f"{action_lines}\n"
        )
