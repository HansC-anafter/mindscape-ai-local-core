"""Workflow response generation helpers."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from backend.app.capabilities.core_llm.services.generate import run as llm_generate
from backend.app.models.playbook import HandoffPlan, PlaybookKind
from backend.app.services.handoff_plan_builder import HandoffPlanBuilder
from backend.app.services.i18n_service import I18nService

logger = logging.getLogger(__name__)


async def generate_workflow_response(
    *,
    generator: Any,
    user_input: str,
    intent_result: Any,
    context: Optional[Dict[str, Any]] = None,
    locale: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate LLM response that may include a handoff plan."""
    provider = generator._ensure_llm_provider()
    if not provider:
        return {
            "message": "I understand your request, but I need an LLM provider to generate a workflow plan.",
            "handoff_plan": None,
        }

    if not intent_result.is_multi_step or not intent_result.workflow_steps:
        return {
            "message": await generator._generate_single_step_response(
                user_input,
                intent_result,
                context,
                locale,
            ),
            "handoff_plan": None,
        }

    handoff_plan_builder = HandoffPlanBuilder()
    context_dict = context or {}
    if intent_result.playbook_context:
        context_dict.update(intent_result.playbook_context)

    try:
        handoff_plan = handoff_plan_builder.build_handoff_plan(
            simplified_steps=intent_result.workflow_steps,
            context=context_dict,
            estimated_duration=None,
        )
    except Exception as exc:
        logger.warning("Failed to build HandoffPlan: %s", exc)
        return {
            "message": "I understand your request, but encountered an error planning the workflow.",
            "handoff_plan": None,
        }

    system_prompt = """You are a helpful AI assistant that understands user requests and creates execution plans.

When the user requests a multi-step workflow, you should:
1. Acknowledge the request in a friendly, natural way
2. Briefly explain what steps will be executed
3. Include a HandoffPlan in <playbook_handoff>...</playbook_handoff> tags

The HandoffPlan should be valid JSON matching this structure:
{
  "steps": [
    {
      "playbook_code": "playbook_name",
      "kind": "user_workflow" or "system_tool",
      "interaction_mode": ["silent", "needs_review", or "conversational"],
      "inputs": {...},
      "input_mapping": {...}
    }
  ],
  "context": {...},
  "estimated_duration": 300
}

Be concise and natural in your response. The HandoffPlan is for the system, not the user."""
    workflow_summary = generator._format_workflow_summary(handoff_plan)
    user_prompt = f"""User request: "{user_input}"

I have identified this as a multi-step workflow with the following steps:
{workflow_summary}

Generate a natural response that:
1. Acknowledges the request
2. Explains what will be done
3. Includes the complete HandoffPlan in <playbook_handoff> tags

HandoffPlan JSON:
{json.dumps(handoff_plan.model_dump(), indent=2, ensure_ascii=False)}"""

    try:
        result = await llm_generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            llm_provider=provider,
            target_language=locale or generator.default_locale,
        )
        response_text = result.get("text", "").strip()
        if not response_text:
            response_text = (
                f"I'll help you with that. I've planned a workflow with {len(handoff_plan.steps)} steps."
            )
        return {"message": response_text, "handoff_plan": handoff_plan}
    except Exception as exc:
        logger.warning("Failed to generate workflow response: %s", exc)
        return {
            "message": f"I'll help you with that. I've planned a workflow with {len(handoff_plan.steps)} steps.",
            "handoff_plan": handoff_plan,
        }


async def generate_single_step_response(
    *,
    user_input: str,
    intent_result: Any,
    context: Optional[Dict[str, Any]],
    locale: Optional[str],
) -> str:
    """Generate response for single-step requests."""
    del user_input, context, locale
    if intent_result.selected_playbook_code:
        return f"I'll help you with that using the {intent_result.selected_playbook_code} playbook."
    return "I understand your request."


def format_workflow_summary(*, handoff_plan: HandoffPlan) -> str:
    """Format workflow steps as a readable summary."""
    summary_parts = []
    for index, step in enumerate(handoff_plan.steps, 1):
        kind_label = (
            "System tool" if step.kind == PlaybookKind.SYSTEM_TOOL else "User workflow"
        )
        summary_parts.append(f"{index}. {kind_label}: {step.playbook_code}")
    return "\n".join(summary_parts)


async def generate_workflow_summary(
    *,
    generator: Any,
    workflow_result: Dict[str, Any],
    handoff_plan: HandoffPlan,
    locale: Optional[str] = None,
) -> str:
    """Generate user-friendly summary of workflow execution results."""
    provider = generator._ensure_llm_provider()
    if not provider:
        i18n = I18nService(default_locale=locale or generator.default_locale)
        return i18n.t(
            "conversation_orchestrator",
            "workflow.completed",
            fallback="Workflow completed successfully",
        )

    steps_results = workflow_result.get("steps", {})
    completed_steps = [
        key for key, value in steps_results.items() if value.get("status") == "completed"
    ]
    failed_steps = [
        key for key, value in steps_results.items() if value.get("status") == "error"
    ]
    system_prompt = """You are a helpful AI assistant summarizing workflow execution results.

Generate a concise, natural summary that:
1. Acknowledges completion of the workflow
2. Highlights key results from each step
3. Mentions any errors if they occurred
4. Is friendly and informative
5. Is 2-3 sentences long

Be specific about what was accomplished."""
    workflow_summary = f"""Workflow executed with {len(handoff_plan.steps)} steps.

Completed steps: {', '.join(completed_steps) if completed_steps else 'None'}
Failed steps: {', '.join(failed_steps) if failed_steps else 'None'}

Step results:
"""
    for step_code, result in steps_results.items():
        status = result.get("status", "unknown")
        outputs = result.get("outputs", {})
        workflow_summary += f"- {step_code}: {status}"
        if outputs:
            output_keys = list(outputs.keys())[:3]
            workflow_summary += f" (outputs: {', '.join(output_keys)})"
        workflow_summary += "\n"

    user_prompt = f"""The following workflow has been executed:

{workflow_summary}

Generate a natural summary message for the user."""

    try:
        result = await llm_generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            llm_provider=provider,
            target_language=locale or generator.default_locale,
        )
        summary = result.get("text", "").strip()
        if summary:
            return summary
    except Exception as exc:
        logger.warning("Failed to generate workflow summary: %s", exc)

    i18n = I18nService(default_locale=locale or generator.default_locale)
    return i18n.t(
        "conversation_orchestrator",
        "workflow.completed",
        fallback="Workflow completed successfully",
    )
