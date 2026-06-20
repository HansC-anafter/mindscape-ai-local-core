"""JSON parsing and playbook-code validation for execution plans."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Callable, Dict, List, Optional

from backend.app.services.execution_plan_context import (
    _coerce_chat_text,
    _resolve_governed_chat_inputs,
)
from backend.app.services.llm.workspace_routed_chat import (
    chat_completion_with_workspace_route,
)

logger = logging.getLogger(__name__)


def _parse_plan_json(response: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from an LLM response."""
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                first_newline = cleaned.find("\n")
                if first_newline > 0:
                    cleaned = cleaned[first_newline:].strip()
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()

            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = cleaned[start:end]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        f"[ExecutionPlanGenerator] JSON parse error at position {exc.pos}: {exc.msg}"
                    )
                    logger.warning(
                        f"[ExecutionPlanGenerator] JSON snippet around error: {json_str[max(0, exc.pos-50):exc.pos+50]}"
                    )
        except Exception as exc:
            logger.warning(
                f"[ExecutionPlanGenerator] Error during JSON extraction: {exc}"
            )

    logger.warning(
        f"[ExecutionPlanGenerator] Failed to parse JSON from response (first 500 chars): {response[:500]}"
    )
    logger.warning(f"[ExecutionPlanGenerator] Response length: {len(response)} chars")
    return None


async def _validate_and_reevaluate_plan(
    plan_data: Dict[str, Any],
    available_playbooks: Optional[List[Dict[str, Any]]],
    user_request: str,
    execution_mode: str,
    expected_artifacts: Optional[List[str]],
    llm_provider: Any,
    model_name: str,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    chat_completion_fn: Callable[..., Any] = chat_completion_with_workspace_route,
    resolve_governed_chat_inputs_fn: Callable[[Any], tuple[Any, Any]] = _resolve_governed_chat_inputs,
    coerce_chat_text_fn: Callable[[Any], str] = _coerce_chat_text,
) -> Dict[str, Any]:
    """
    Validate playbook codes and re-evaluate if invalid codes are found.

    If the LLM generated invalid playbook codes, ask it to re-evaluate and
    choose from available playbooks.
    """
    if not available_playbooks:
        return plan_data

    valid_playbook_codes = set()
    playbook_code_to_info = {}
    for playbook in available_playbooks:
        code = playbook.get("playbook_code", playbook.get("code", ""))
        if code:
            valid_playbook_codes.add(code.lower())
            playbook_code_to_info[code.lower()] = {
                "code": code,
                "name": playbook.get("name", code),
                "description": playbook.get("description", "")[:100],
            }

    special_packs = {"intent_extraction", "semantic_seeds"}
    invalid_steps = []
    steps = plan_data.get("steps", [])

    for index, step in enumerate(steps):
        playbook_code = step.get("playbook_code")
        if playbook_code:
            playbook_code_lower = playbook_code.lower()
            is_valid = (
                playbook_code_lower in valid_playbook_codes
                or playbook_code_lower in special_packs
            )

            if not is_valid:
                invalid_steps.append(
                    {
                        "index": index,
                        "step_id": step.get("step_id", f"S{index+1}"),
                        "intent": step.get("intent", ""),
                        "invalid_playbook_code": playbook_code,
                        "reasoning": step.get("reasoning", ""),
                    }
                )

    if not invalid_steps:
        return plan_data

    logger.warning(
        f"[ExecutionPlanGenerator] Found {len(invalid_steps)} steps with invalid playbook codes. "
        "Re-evaluating with LLM..."
    )
    print(
        f"[ExecutionPlanGenerator] WARNING: Found {len(invalid_steps)} invalid playbook codes, re-evaluating...",
        file=sys.stderr,
    )

    if progress_callback:
        invalid_codes = [step["invalid_playbook_code"] for step in invalid_steps]
        progress_callback(
            "reevaluation_started",
            {
                "message_key": "execution_plan.reevaluation_started",
                "message_params": {"count": len(invalid_steps)},
                "invalid_codes": invalid_codes,
                "invalid_steps": [
                    {
                        "step_id": step["step_id"],
                        "intent": step["intent"],
                        "invalid_code": step["invalid_playbook_code"],
                    }
                    for step in invalid_steps
                ],
                "available_playbook_count": len(available_playbooks),
            },
        )

    valid_codes_list = sorted([info["code"] for info in playbook_code_to_info.values()])
    reevaluation_prompt = f"""You previously generated an execution plan, but some steps used invalid playbook codes that are not in the available list.

## Invalid Playbook Codes Found:
{chr(10).join([f"- Step {step['step_id']} (intent: {step['intent']}): '{step['invalid_playbook_code']}' - {step['reasoning']}" for step in invalid_steps])}

## Available Playbook Codes (you MUST use only these):
{chr(10).join([f"- {code}: {playbook_code_to_info[code.lower()]['name']} - {playbook_code_to_info[code.lower()]['description']}" for code in valid_codes_list])}

## Original User Request:
{user_request}

## Your Task:
Please correct the invalid playbook codes in the following execution plan. For each step with an invalid playbook_code:
1. Find the most suitable playbook from the available list above
2. Replace the invalid code with the correct one
3. If no playbook matches, set playbook_code to null and use tool_name instead

## Current Execution Plan (JSON):
{json.dumps(plan_data, indent=2)}

Return the CORRECTED execution plan as JSON with the same structure. Only fix the invalid playbook codes, keep everything else the same.
"""

    try:
        from backend.app.shared.llm_utils import build_prompt

        messages = build_prompt(
            system_prompt="You are an Execution Planning Agent that corrects invalid playbook codes. Output only valid JSON.",
            user_prompt=reevaluation_prompt,
        )

        provider, llm_provider_manager = resolve_governed_chat_inputs_fn(llm_provider)
        response = await chat_completion_fn(
            messages=messages,
            workspace_id=workspace_id,
            profile_id=profile_id or "default-user",
            provider=provider,
            llm_provider_manager=llm_provider_manager,
            model=model_name,
            purpose="execution_plan_reevaluation",
            stage_name="plan_generation",
            risk_level="read",
            temperature=0.2,
            max_tokens=4000,
        )
        corrected_plan_data = _parse_plan_json(coerce_chat_text_fn(response))
        if corrected_plan_data:
            logger.info(
                f"[ExecutionPlanGenerator] Successfully re-evaluated plan, corrected {len(invalid_steps)} invalid playbook codes"
            )
            print(
                f"[ExecutionPlanGenerator] Successfully corrected {len(invalid_steps)} invalid playbook codes",
                file=sys.stderr,
            )

            if progress_callback:
                progress_callback(
                    "reevaluation_completed",
                    {
                        "message_key": "execution_plan.reevaluation_completed",
                        "message_params": {"count": len(invalid_steps)},
                        "corrected_count": len(invalid_steps),
                    },
                )

            return corrected_plan_data

        logger.warning(
            "[ExecutionPlanGenerator] Failed to parse re-evaluation response, using original plan with filtered steps"
        )
    except Exception as exc:
        logger.warning(
            f"[ExecutionPlanGenerator] Re-evaluation failed: {exc}, using original plan with filtered steps",
            exc_info=True,
        )

    logger.info(
        f"[ExecutionPlanGenerator] Removing {len(invalid_steps)} steps with invalid playbook codes"
    )
    invalid_indexes = {step["index"] for step in invalid_steps}
    valid_steps = [
        step for index, step in enumerate(steps) if index not in invalid_indexes
    ]
    plan_data["steps"] = valid_steps

    return plan_data
