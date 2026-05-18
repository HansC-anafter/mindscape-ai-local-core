"""Meeting output rendering helpers for MeetingPromptsMixin."""

from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.meeting.prompt_core.directives import (
    _FULL_REVIEW_NATIVE_SPATIAL_ROLE_OVERRIDES,
)


class MeetingPromptOutputMixin:
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

        topic = self._extract_meeting_topic(user_message)

        decision_summary = decision[:300]
        if len(decision) > 300:
            decision_summary += "\n\n_(...truncated)_"

        risk_lines = []
        for note in critic_notes:
            summary = note[:200]
            if len(note) > 200:
                summary += "..."
            risk_lines.append(f"- {summary}")
        risk_text = "\n".join(risk_lines) or "- None"

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

        agenda_items = self.session.agenda or [user_message]
        agenda_text = "\n".join([f"- {a}" for a in agenda_items])

        return (
            f"# {topic}\n"
            f"_Meeting {self.session.id[:8]} · {status} · {self.session.round_count} rounds_\n\n"
            f"## Agenda\n{agenda_text}\n\n"
            f"## Decisions\n{decision_summary}\n\n"
            f"## Risks & Concerns\n{risk_text}\n\n"
            "## Action Items\n"
            "| # | Task | Assigned To | Priority |\n"
            "|---|------|-------------|----------|\n"
            f"{action_lines}\n"
        )

    def _assemble_system_message(
        self,
        role_def,
        *,
        role_id: Optional[str] = None,
        user_message: str = "",
    ) -> str:
        """Assemble full system message from role definition fields.

        Combines system_prompt + responsibility_boundary + critical_rules
        + communication_style + success_metrics into a structured block.
        """
        override = None
        if role_id and self._is_full_review_native_spatial_meeting(user_message):
            override = _FULL_REVIEW_NATIVE_SPATIAL_ROLE_OVERRIDES.get(role_id)

        system_prompt = (
            str(override.get("system_prompt"))
            if isinstance(override, dict) and override.get("system_prompt")
            else role_def.system_prompt
        )
        critical_rules = (
            list(override.get("critical_rules") or [])
            if isinstance(override, dict) and override.get("critical_rules")
            else role_def.critical_rules
        )
        communication_style = (
            str(override.get("communication_style"))
            if isinstance(override, dict) and override.get("communication_style")
            else role_def.communication_style
        )
        success_metrics = (
            list(override.get("success_metrics") or [])
            if isinstance(override, dict) and override.get("success_metrics")
            else role_def.success_metrics
        )

        parts = []
        if system_prompt:
            parts.append(system_prompt)

        if role_def.responsibility_boundary:
            parts.append(
                f"\nResponsibility boundary: {role_def.responsibility_boundary}. "
                "Stay strictly within this boundary."
            )

        if critical_rules:
            rules_text = "\n".join(f"- {r}" for r in critical_rules)
            parts.append(f"\nCritical rules you MUST follow:\n{rules_text}")

        if communication_style:
            parts.append(f"\nCommunication style: {communication_style}")

        if success_metrics:
            metrics_text = "\n".join(f"- {m}" for m in success_metrics)
            parts.append(f"\nYour output is successful when:\n{metrics_text}")

        return "\n".join(parts)

    def _extract_meeting_topic(self, user_message: str) -> str:
        """Extract a concise topic line for meeting minutes title."""
        project_ctx = getattr(self, "_project_context", "")
        if project_ctx:
            for line in project_ctx.split("\n"):
                if line.startswith("Project:"):
                    return line.replace("Project:", "").strip() + " — Meeting Minutes"

        topic = user_message[:60]
        if len(user_message) > 60:
            topic += "..."
        return f"Meeting Minutes — {topic}"
