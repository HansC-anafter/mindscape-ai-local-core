"""Turn prompt construction helpers for MeetingPromptsMixin."""

import json
import logging
from typing import List, Optional

from backend.app.services.orchestration.meeting.prompt_core.directives import (
    _FULL_REVIEW_NATIVE_SPATIAL_CRITIC_DIRECTIVE,
    _FULL_REVIEW_NATIVE_SPATIAL_FACILITATOR_DIRECTIVE,
    _FULL_REVIEW_NATIVE_SPATIAL_PLANNER_DIRECTIVE,
    _NATIVE_SPATIAL_PLANNER_DIRECTIVE,
    _ROLE_TURN_DIRECTIVES,
)

logger = logging.getLogger(__name__)


class MeetingPromptTurnMixin:
    def _build_turn_prompt(
        self,
        role_id: str,
        round_num: int,
        user_message: str,
        decision: Optional[str],
        planner_proposals: List[str],
        critic_notes: List[str],
    ) -> str:
        """Build the full prompt for a single deliberation role turn."""
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
        project_id = getattr(self, "project_id", None) or getattr(
            self.session, "project_id", None
        )
        minimal_native_spatial_context = self._is_full_review_native_spatial_meeting(
            user_message
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

        asset_map_block = ""
        asset_map_ctx = getattr(self, "_asset_map_context", "")
        if asset_map_ctx and not minimal_native_spatial_context:
            asset_map_block = (
                f"=== Workspace Asset Map ===\n"
                f"{asset_map_ctx}\n"
                f"=== End Asset Map ===\n\n"
                f"Use the asset map as context for understanding what data "
                f"is already available. All action items MUST target the "
                f"current workspace — do NOT set target_workspace_id.\n\n"
            )

        common = locale_directive + project_block + asset_map_block

        tool_ctx = "" if minimal_native_spatial_context else self._build_tool_inventory_block()
        if tool_ctx:
            common += (
                f"=== Available Tools ===\n" f"{tool_ctx}\n" f"=== End Tools ===\n\n"
            )
        _tool_line_count = len(tool_ctx.strip().splitlines()) if tool_ctx else 0
        logger.debug(
            "meeting_tool_inventory role=%s workspace=%s tool_lines=%d session=%s",
            role_id,
            getattr(getattr(self, "session", None), "workspace_id", "?"),
            _tool_line_count,
            getattr(getattr(self, "session", None), "id", "?"),
        )

        uploaded = getattr(self, "_uploaded_files", [])
        if uploaded and not minimal_native_spatial_context:
            file_lines = []
            for f in uploaded[:10]:
                name = f.get("file_name") or f.get("file_id", "unknown")
                ftype = f.get("file_type", "")
                file_lines.append(f"  - {name} ({ftype})" if ftype else f"  - {name}")
            common += (
                f"=== Uploaded Files ===\n"
                + "\n".join(file_lines)
                + "\n=== End Files ===\n\n"
            )

        common += (
            f"Meeting session: {self.session.id}\n"
            f"Workspace ID: {self.session.workspace_id}\n"
            f"Project ID: {project_id or '(none)'}\n"
            f"Round: {round_num}/{max(1, self.session.max_rounds)}\n"
            f"Agenda:\n{agenda_text}\n\n"
            f"User request:\n{user_message}\n\n"
            f"Current decision draft:\n{decision or '(not finalized)'}\n\n"
            f"Latest planner proposal:\n{latest_proposal}\n\n"
            f"Latest critic note:\n{latest_critic}\n\n"
            f"Recent turns:\n{history}\n\n"
        )
        if not minimal_native_spatial_context:
            affordance_block = self._build_request_affordance_block()
            if affordance_block:
                common += affordance_block
        if minimal_native_spatial_context:
            contract_block = self._build_native_spatial_contract_block()
            if contract_block:
                common += contract_block

        lens_ctx = "" if minimal_native_spatial_context else self._build_lens_context()
        if lens_ctx:
            common += (
                f"=== Active Lens ===\n"
                f"{lens_ctx}\n"
                f"=== End Lens ===\n\n"
                f"Consider the active lens dimensions when framing your response.\n\n"
            )

        intent_ids = getattr(self, "_active_intent_ids", [])
        if intent_ids and not minimal_native_spatial_context:
            try:
                intents = self.store.list_intents(
                    self.profile_id,
                    project_id=project_id,
                )
                active = [i for i in intents if i.id in intent_ids]
                if active:
                    intent_lines = []
                    for i in active[:5]:
                        status_val = (
                            i.status.value
                            if hasattr(i.status, "value")
                            else str(i.status)
                        )
                        intent_lines.append(
                            f"  - {i.title} [{status_val}] "
                            f"(progress: {i.progress_percentage}%)"
                        )
                    common += (
                        f"=== Active Intents ===\n"
                        + "\n".join(intent_lines)
                        + "\n=== End Intents ===\n\n"
                    )
            except Exception as exc:
                logger.warning("Failed to inject intents into prompt: %s", exc)

        prev_ctx = (
            "" if minimal_native_spatial_context else self._build_previous_decisions_context()
        )
        if prev_ctx:
            common += (
                f"=== Previous Meeting Decisions ===\n"
                f"{prev_ctx}\n"
                f"=== End Previous Decisions ===\n\n"
            )

        workflow_evidence_ctx = (
            ""
            if minimal_native_spatial_context
            else getattr(self, "_workflow_evidence_context", "")
        )
        if workflow_evidence_ctx:
            common += (
                f"=== Workflow Evidence ===\n"
                f"{workflow_evidence_ctx}\n"
                f"=== End Workflow Evidence ===\n\n"
            )

        ws_ctx = "" if minimal_native_spatial_context else self._build_workspace_instruction_block()
        if ws_ctx:
            common += (
                "=== Workspace Context (Reference) ===\n"
                "The following is background context from the workspace. "
                "It does NOT override your deliberation role or the project agenda.\n"
                f"{ws_ctx}\n"
                "=== End Context ===\n\n"
            )

        if role_id == "facilitator":
            if minimal_native_spatial_context:
                return common + _FULL_REVIEW_NATIVE_SPATIAL_FACILITATOR_DIRECTIVE
            return common + _ROLE_TURN_DIRECTIVES["facilitator"]
        if role_id == "planner":
            file_directive = ""
            if getattr(self, "_uploaded_files", None):
                file_directive = (
                    "CONSTRAINT: Uploaded files are present. Your plan MUST include "
                    "at least one step that uses a tool or playbook from Available "
                    "Tools to process these files into structured artifacts. "
                )
            contract_block = ""
            contract = getattr(self, "_request_contract", None)
            if (
                not minimal_native_spatial_context
                and contract
                and hasattr(contract, "deliverables")
                and contract.deliverables
            ):
                d_lines = []
                for d in contract.deliverables:
                    d_lines.append(f"  - {d.id}: {d.name} (qty={d.quantity})")
                contract_block = (
                    f"=== Contract Deliverables ===\n"
                    + "\n".join(d_lines)
                    + "\n=== End Deliverables ===\n\n"
                    "Your workstreams MUST reference these deliverable IDs "
                    "in produces_deliverables / reviews_deliverables fields.\n\n"
                )
            planner_directive = (
                _NATIVE_SPATIAL_PLANNER_DIRECTIVE
                if self._use_native_spatial_planner_mode(role_id, user_message)
                else (
                    _FULL_REVIEW_NATIVE_SPATIAL_PLANNER_DIRECTIVE
                    if minimal_native_spatial_context
                    else _ROLE_TURN_DIRECTIVES["planner"]
                )
            )
            return common + file_directive + contract_block + planner_directive
        if role_id == "critic":
            if minimal_native_spatial_context:
                return common + _FULL_REVIEW_NATIVE_SPATIAL_CRITIC_DIRECTIVE
            file_check = ""
            if getattr(self, "_uploaded_files", None):
                file_check = (
                    "MANDATORY CHECK: Verify the planner's proposal includes "
                    "tool or playbook usage for the uploaded files. If the plan "
                    "only produces text analysis without using available tools, "
                    "flag this as a critical gap. "
                )
            return common + file_check + _ROLE_TURN_DIRECTIVES["critic"]
        playbooks_cache = getattr(self, "_available_playbooks_cache", "")
        playbook_block = ""
        if playbooks_cache and role_id == "executor":
            playbook_block = (
                f"=== Available Playbooks ===\n"
                f"{playbooks_cache}\n"
                f"=== End Playbooks ===\n\n"
            )

        tool_ctx = self._build_tool_inventory_block()
        has_explicit_bindings = self._has_workspace_tool_bindings()
        has_rag_tools = bool(getattr(self, "_rag_tool_cache", []))
        tool_constraint = ""
        if has_explicit_bindings or has_rag_tools:
            tool_constraint = (
                "MANDATORY: The workspace has been configured with specific tools / "
                "playbooks (see Available Tools / Available Playbooks above). "
                "At least one action item in your JSON array MUST have a non-null "
                "tool_name (chosen exactly from Available Tools) OR a non-null "
                "playbook_code (chosen exactly from Available Playbooks). "
                "Action items with both tool_name=null AND playbook_code=null are "
                "only allowed when no configured tool is relevant to that specific step. "
            )

        return (
            common
            + playbook_block
            + "As executor, produce a JSON array of action items covering all required steps. "
            'Schema: [{"title":"...","description":"...","assigned_to":"executor",'
            '"priority":"low|medium|high","playbook_code":null,'
            '"tool_name":null,"input_params":null,"blocked_by":null}] '
            "playbook_code MUST be selected from Available Playbooks above, or null "
            "if none match. "
            "tool_name is for direct tool invocation without a playbook. "
            "Use tool_name exactly as listed in Available Tools, including the "
            "namespace prefix (e.g., pack.tool). "
            "blocked_by is a list of action item indices (0-based) that must complete first. "
            + tool_constraint
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
        self, role_id: str, round_num: int, user_message: str
    ) -> str:
        """Generate a deterministic fallback turn when LLM is unavailable."""
        if role_id == "facilitator":
            return (
                f"Round {round_num} facilitation summary for '{user_message[:80]}'. "
                "Planner and critic inputs consolidated."
            )
        if role_id == "planner":
            return f"Proposal R{round_num}: execute incrementally, track evidence, and verify outcomes."
        if role_id == "critic":
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
        """Check whether the meeting has converged.

        Uses RoundVerdict.try_parse() for structured convergence checking.
        Stores the parsed verdict on self._last_round_verdict for downstream
        consumers (L2/L3) to inspect confidence and remaining concerns.
        """
        from backend.app.models.layer_artifacts import RoundVerdict

        if round_num >= max_rounds:
            self._last_round_verdict = RoundVerdict(
                converged=True,
                confidence=0.5,
                reason="timebox_exhausted",
                remaining_concerns=["Max rounds reached without explicit convergence"],
            )
            return True

        verdict = RoundVerdict.try_parse(facilitator_text)
        self._last_round_verdict = verdict

        if round_num >= 2 and verdict.converged and verdict.coverage_pass:
            return True

        if verdict.converged and not verdict.coverage_pass:
            logger.info("Converge blocked: coverage_pass=False")
            return False

        return False
