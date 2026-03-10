"""
Meeting IR Compiler Mixin.

Compiles MeetingResult output (decision + action_items) into structured
TaskIR for downstream dispatch and persistence.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class MeetingIRCompilerMixin:
    """Compile meeting output into TaskIR for downstream dispatch."""

    def _compile_to_task_ir(
        self,
        decision: str,
        action_items: List[Dict[str, Any]],
        handoff_in: Optional[Any] = None,
        *,
        action_intents: Optional[List[Any]] = None,
    ) -> Any:
        """Convert meeting output into structured TaskIR.

        Maps action_items to PhaseIR instances and populates governance
        fields from HandoffIn via GovernanceContext if present.

        When ``action_intents`` is provided (Phase 1+), uses typed
        ActionIntent objects with invariants:
        - INV-2: phase_id = intent_id (stable identity)
        - INV-4: depends_on is passthrough (no auto-sequential)

        Args:
            decision: Final meeting decision text.
            action_items: Action items from the meeting (legacy dicts).
            handoff_in: Optional HandoffIn that triggered this meeting.
            action_intents: Optional typed ActionIntent list (Phase 1+).

        Returns:
            Compiled TaskIR instance.
        """
        from backend.app.models.task_ir import (
            TaskIR,
            PhaseIR,
            PhaseStatus,
            TaskStatus,
            ExecutionMetadata,
            GovernanceContext,
        )

        task_id = f"task_{uuid.uuid4().hex[:16]}"

        # Build phases — use ActionIntents if available (Phase 1+)
        if action_intents:
            phases = self._build_phases_from_intents(action_intents)
        else:
            phases = self._build_phases_from_dicts(action_items)

        # If no phases, create a single phase from the decision
        if not phases:
            phases.append(
                PhaseIR(
                    id="decision_0",
                    name="Execute Decision",
                    description=decision,
                    status=PhaseStatus.PENDING,
                )
            )

        # Build metadata with governance from HandoffIn
        metadata = ExecutionMetadata()

        if handoff_in is not None:
            gov = GovernanceContext(
                goals=getattr(handoff_in, "goals", None) or [],
                non_goals=getattr(handoff_in, "non_goals", None),
                acceptance_tests=getattr(handoff_in, "acceptance_tests", None),
                risk_profile={
                    "risk_notes": getattr(handoff_in, "risk_notes", None) or []
                },
                handoff_id=getattr(handoff_in, "handoff_id", None),
            )

            constraints = getattr(handoff_in, "constraints", None)
            if constraints is not None:
                gov.constraints = (
                    constraints.model_dump()
                    if hasattr(constraints, "model_dump")
                    else constraints
                )

            deliverables = getattr(handoff_in, "deliverables", None)
            if deliverables:
                gov.deliverables = [
                    d.model_dump() if hasattr(d, "model_dump") else d
                    for d in deliverables
                ]

            metadata.set_governance(gov)

        # Resolve workspace ID from session or handoff
        workspace_id = ""
        if handoff_in and getattr(handoff_in, "workspace_id", None):
            workspace_id = handoff_in.workspace_id
        elif hasattr(self, "session"):
            workspace_id = getattr(self.session, "workspace_id", "")

        # Resolve actor ID from profile
        actor_id = getattr(self, "profile_id", "meeting_engine")

        task_ir = TaskIR(
            task_id=task_id,
            intent_instance_id=getattr(self, "session", None)
            and self.session.id
            or task_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            current_phase=phases[0].id if phases else None,
            status=TaskStatus.PENDING,
            phases=phases,
            artifacts=[],
            metadata=metadata,
        )

        logger.info(
            "Compiled TaskIR %s with %d phases from meeting session",
            task_id,
            len(phases),
        )
        return task_ir

    @staticmethod
    def _build_phases_from_intents(intents: List[Any]) -> List[Any]:
        """Build PhaseIR list from ActionIntent[] (INV-2, INV-4)."""
        from backend.app.models.task_ir import PhaseIR, PhaseStatus

        phases = []
        for intent in intents:
            engine = intent.engine
            if not engine:
                if intent.playbook_code:
                    engine = f"playbook:{intent.playbook_code}"
                elif intent.tool_name:
                    engine = f"tool:{intent.tool_name}"
                else:
                    engine = "playbook:generic"

            phase = PhaseIR(
                # INV-2: phase_id = intent_id
                id=intent.intent_id,
                name=intent.title,
                description=intent.description,
                status=PhaseStatus.PENDING,
                preferred_engine=engine,
                # INV-4: passthrough depends_on, no auto-sequential
                depends_on=intent.depends_on,
                target_workspace_id=intent.target_workspace_id,
                asset_refs=intent.asset_refs or [],
                tool_name=intent.tool_name,
                input_params=intent.input_params,
            )
            phases.append(phase)
        return phases

    @staticmethod
    def _build_phases_from_dicts(
        action_items: List[Dict[str, Any]],
    ) -> List[Any]:
        """Build PhaseIR list from legacy action_item dicts (backward compat)."""
        from backend.app.models.task_ir import PhaseIR, PhaseStatus

        phases = []
        for idx, item in enumerate(action_items):
            title = item.get("title") or item.get("action") or f"Action {idx + 1}"
            desc = item.get("description") or item.get("detail") or ""
            engine = item.get("engine") or None
            if not engine:
                playbook_code = item.get("playbook_code")
                if playbook_code:
                    engine = f"playbook:{playbook_code}"
                elif item.get("tool_name"):
                    engine = f"tool:{item['tool_name']}"
                else:
                    engine = "playbook:generic"

            phase = PhaseIR(
                id=f"action_{idx}",
                name=title,
                description=desc,
                status=PhaseStatus.PENDING,
                preferred_engine=engine,
                depends_on=[f"action_{idx - 1}"] if idx > 0 else None,
                target_workspace_id=item.get("target_workspace_id"),
                asset_refs=item.get("asset_refs") or [],
                tool_name=item.get("tool_name"),
                input_params=item.get("input_params"),
                blocked_by=item.get("blocked_by"),
            )
            phases.append(phase)
        return phases
