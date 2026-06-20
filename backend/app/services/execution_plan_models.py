"""ExecutionPlan and TaskPlan construction helpers."""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.workspace import ExecutionPlan, ExecutionStep, TaskPlan
from backend.app.services.execution_plan_context import _utc_now

logger = logging.getLogger(__name__)


def _convert_steps_to_tasks(
    steps: List[ExecutionStep],
    plan_confidence: float = 0.7,
    available_playbooks: Optional[List[Dict[str, Any]]] = None,
) -> List[TaskPlan]:
    """
    Convert ExecutionStep list to TaskPlan list for execution.

    Enables the same ExecutionPlan to be used for UI display and execution.
    """
    valid_playbook_codes = set()
    if available_playbooks:
        for playbook in available_playbooks:
            code = playbook.get("playbook_code", playbook.get("code", ""))
            if code:
                valid_playbook_codes.add(code.lower())

    special_packs = {"intent_extraction", "semantic_seeds"}
    tasks = []
    for step in steps:
        pack_id = None
        if step.playbook_code:
            playbook_code_lower = step.playbook_code.lower()
            is_valid = (
                playbook_code_lower in valid_playbook_codes
                or playbook_code_lower in special_packs
            )

            if not is_valid:
                logger.warning(
                    f"[ExecutionPlanGenerator] Step {step.step_id} (intent: {step.intent}) "
                    f"has invalid playbook_code '{step.playbook_code}' not in available playbooks. "
                    "Skipping task conversion. This step will appear in UI but won't be executed."
                )
                print(
                    f"[ExecutionPlanGenerator] WARNING: Step {step.step_id} skipped - "
                    f"invalid playbook_code='{step.playbook_code}' not in playbook list, intent={step.intent}",
                    file=sys.stderr,
                )
                continue

            pack_id = step.playbook_code
        elif step.tool_name:
            tool_to_pack = {
                "generic_drafting": "content_drafting",
                "drafting": "content_drafting",
                "storyboard": "storyboard",
                "planning": "daily_planning",
                "research": "research",
            }
            pack_id = tool_to_pack.get(step.tool_name, step.tool_name)

        if not pack_id:
            logger.warning(
                f"[ExecutionPlanGenerator] Step {step.step_id} (intent: {step.intent}) "
                "has no playbook_code or tool_name, skipping task conversion. "
                "This step will appear in UI but won't be executed."
            )
            print(
                f"[ExecutionPlanGenerator] WARNING: Step {step.step_id} skipped - "
                f"playbook_code={step.playbook_code}, tool_name={step.tool_name}, intent={step.intent}",
                file=sys.stderr,
            )
            continue

        task_type = "execute"
        if "generate" in step.intent.lower() or "create" in step.intent.lower():
            task_type = "generate_draft"
        elif "extract" in step.intent.lower() or "analyze" in step.intent.lower():
            task_type = "extract_intents"
        elif "plan" in step.intent.lower() or "schedule" in step.intent.lower():
            task_type = "generate_tasks"

        task_plan = TaskPlan(
            pack_id=pack_id,
            task_type=task_type,
            params={
                "intent": step.intent,
                "reasoning": step.reasoning,
                "artifacts": step.artifacts,
                "step_id": step.step_id,
                "depends_on": step.depends_on,
                "llm_analysis": {"confidence": plan_confidence},
            },
            side_effect_level=step.side_effect_level or "readonly",
            auto_execute=not step.requires_confirmation,
            requires_cta=step.requires_confirmation,
        )
        tasks.append(task_plan)
        logger.info(
            f"[ExecutionPlanGenerator] Converted step {step.step_id} to TaskPlan: pack_id={pack_id}, task_type={task_type}"
        )

    return tasks


def _create_execution_plan(
    plan_data: Dict[str, Any],
    workspace_id: str,
    message_id: str,
    execution_mode: str,
    available_playbooks: Optional[List[Dict[str, Any]]] = None,
) -> ExecutionPlan:
    """Create ExecutionPlan from parsed JSON data."""
    steps = []
    for step_data in plan_data.get("steps", []):
        step = ExecutionStep(
            step_id=step_data.get("step_id", f"S{len(steps)+1}"),
            intent=step_data.get("intent", "Execute task"),
            playbook_code=step_data.get("playbook_code"),
            tool_name=step_data.get("tool_name"),
            artifacts=step_data.get("artifacts", []),
            reasoning=step_data.get("reasoning"),
            depends_on=step_data.get("depends_on", []),
            requires_confirmation=step_data.get("requires_confirmation", False),
            side_effect_level=step_data.get("side_effect_level", "readonly"),
            estimated_duration=step_data.get("estimated_duration"),
        )
        steps.append(step)

    plan_confidence = plan_data.get("confidence", 0.7)
    tasks = _convert_steps_to_tasks(
        steps, plan_confidence=plan_confidence, available_playbooks=available_playbooks
    )

    logger.info(
        f"[ExecutionPlanGenerator] Created ExecutionPlan: {len(steps)} steps, {len(tasks)} tasks. "
        f"Steps with playbook_code: {sum(1 for step in steps if step.playbook_code)}, "
        f"Steps with tool_name: {sum(1 for step in steps if step.tool_name)}"
    )
    print(
        f"[ExecutionPlanGenerator] ExecutionPlan created: {len(steps)} steps -> {len(tasks)} tasks. "
        f"Missing playbook_code in {len(steps) - len(tasks)} steps.",
        file=sys.stderr,
    )

    return ExecutionPlan(
        id=str(uuid.uuid4()),
        message_id=message_id,
        workspace_id=workspace_id,
        user_request_summary=plan_data.get("user_request_summary"),
        reasoning=plan_data.get("reasoning"),
        plan_summary=plan_data.get("plan_summary"),
        steps=steps,
        tasks=tasks,
        execution_mode=execution_mode,
        confidence=plan_data.get("confidence", 0.7),
        created_at=_utc_now(),
        project_id=None,
        project_assignment_decision=None,
    )


def _create_minimal_plan(
    user_request: str,
    workspace_id: str,
    message_id: str,
    execution_mode: str,
    expected_artifacts: Optional[List[str]] = None,
) -> ExecutionPlan:
    """Create a minimal plan without LLM."""
    step = ExecutionStep(
        step_id="S1",
        intent="Process user request",
        playbook_code=None,
        tool_name="generic_drafting",
        artifacts=expected_artifacts or ["md"],
        reasoning="No specific playbook matched, using generic drafting",
        depends_on=[],
        requires_confirmation=False,
        side_effect_level="soft_write",
    )

    tasks = _convert_steps_to_tasks([step], plan_confidence=0.5)

    return ExecutionPlan(
        id=str(uuid.uuid4()),
        message_id=message_id,
        workspace_id=workspace_id,
        user_request_summary=user_request[:100],
        reasoning="Minimal plan generated without LLM analysis",
        plan_summary="Processing request with generic drafting",
        steps=[step],
        tasks=tasks,
        execution_mode=execution_mode,
        confidence=0.5,
        created_at=_utc_now(),
    )
