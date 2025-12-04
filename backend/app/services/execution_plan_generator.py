"""
Execution Plan Generator

Generates structured ExecutionPlan (Chain-of-Thought) from user requests.
This is the "先想再做" (think before act) component of Execution Mode.

The generated plan:
1. Shows what the LLM decided to do
2. Provides reasoning for each step
3. Lists expected artifacts
4. Can be recorded as EXECUTION_PLAN MindEvent for traceability

See: docs-internal/architecture/workspace-llm-agent-execution-mode.md
"""

import json
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

from backend.app.models.workspace import ExecutionPlan, ExecutionStep, TaskPlan

logger = logging.getLogger(__name__)

# Prompt template for generating execution plan
EXECUTION_PLAN_PROMPT = """You are an Execution Planning Agent. Your task is to analyze the user's request
and create a structured execution plan BEFORE taking any action.

## User Request
{user_request}

## Workspace Context
- Execution Mode: {execution_mode}
- Expected Artifacts: {expected_artifacts}
- Available Playbooks: {available_playbooks}

## Instructions
Create a JSON execution plan with the following structure:
{{
  "user_request_summary": "Brief summary of what user wants",
  "reasoning": "Your overall reasoning for how to approach this request",
  "plan_summary": "One sentence summary for display to user",
  "confidence": 0.0-1.0,
  "steps": [
    {{
      "step_id": "S1",
      "intent": "What this step accomplishes",
      "playbook_code": "playbook_name or null",
      "tool_name": "tool_name or null",
      "artifacts": ["expected", "artifact", "types"],
      "reasoning": "Why this step is needed",
      "depends_on": [],
      "requires_confirmation": false,
      "side_effect_level": "readonly|soft_write|external_write",
      "estimated_duration": "30s"
    }}
  ]
}}

## Rules
1. Break complex requests into clear steps
2. Identify which playbook/tool best fits each step
3. List expected artifacts for each step
4. Mark steps that need user confirmation (soft_write, external_write)
5. Set realistic confidence (lower if request is ambiguous)
6. If no playbook matches, still create steps with tool_name or "generic_drafting"

Return ONLY valid JSON, no markdown fences or explanation.
"""


async def generate_execution_plan(
    user_request: str,
    workspace_id: str,
    message_id: str,
    execution_mode: str = "execution",
    expected_artifacts: Optional[List[str]] = None,
    available_playbooks: Optional[List[Dict[str, Any]]] = None,
    llm_provider: Any = None,
    model_name: Optional[str] = None
) -> Optional[ExecutionPlan]:
    """
    Generate a structured ExecutionPlan from user request using LLM

    This is the Chain-of-Thought generation step that happens BEFORE execution.

    Args:
        user_request: User's message/request
        workspace_id: Workspace ID
        message_id: Message/event ID
        execution_mode: qa/execution/hybrid
        expected_artifacts: Expected artifact types for this workspace
        available_playbooks: List of available playbooks
        llm_provider: LLM provider instance
        model_name: Model to use

    Returns:
        ExecutionPlan or None if generation fails
    """
    # For QA mode, skip plan generation
    if execution_mode == "qa":
        logger.info("[ExecutionPlanGenerator] Skipping plan generation for QA mode")
        return None

    # Validate required parameters
    if not model_name:
        error_msg = "Cannot generate execution plan: model_name is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not llm_provider:
        error_msg = "Cannot generate execution plan: llm_provider is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Format available playbooks for prompt
    playbooks_str = "None available"
    if available_playbooks:
        playbooks_list = []
        for pb in available_playbooks:
            code = pb.get('playbook_code', pb.get('code', 'unknown'))
            name = pb.get('name', code)
            desc = pb.get('description', '')[:100]
            outputs = pb.get('output_types', [])
            playbooks_list.append(f"- {code}: {name} (outputs: {outputs}) - {desc}")
        playbooks_str = "\n".join(playbooks_list) if playbooks_list else "None available"

    # Build prompt
    prompt = EXECUTION_PLAN_PROMPT.format(
        user_request=user_request,
        execution_mode=execution_mode,
        expected_artifacts=expected_artifacts or ["various"],
        available_playbooks=playbooks_str
    )

    try:
        from backend.app.shared.llm_utils import build_prompt
        messages = build_prompt(
            system_prompt="You are an Execution Planning Agent that outputs JSON.",
            user_prompt=prompt
        )

        # Get provider from llm_provider manager based on model name
        provider_name = None
        if "gemini" in model_name.lower():
            provider_name = "vertex-ai"
        elif "gpt" in model_name.lower() or "o1" in model_name.lower() or "o3" in model_name.lower():
            provider_name = "openai"
        elif "claude" in model_name.lower():
            provider_name = "anthropic"

        if not provider_name:
            error_msg = f"Cannot determine provider for model '{model_name}'. Supported models: gemini-*, gpt-*, o1-*, o3-*, claude-*"
            logger.error(error_msg)
            raise ValueError(error_msg)

        provider = llm_provider.get_provider(provider_name)
        if not provider:
            error_msg = f"Provider '{provider_name}' not available for model '{model_name}'. Please check your API configuration."
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not hasattr(provider, 'chat_completion'):
            error_msg = f"Provider '{provider_name}' does not support chat_completion"
            logger.error(error_msg)
            raise ValueError(error_msg)

        response = await provider.chat_completion(
            messages=messages,
            model=model_name,
            temperature=0.3,  # Lower temperature for more consistent plans
            max_tokens=4000  # Increased to handle complex execution plans
        )

        logger.info(f"[ExecutionPlanGenerator] Received LLM response, length: {len(response)} chars")
        logger.debug(f"[ExecutionPlanGenerator] Response preview (first 500 chars): {response[:500]}")

        # Parse JSON response
        plan_data = _parse_plan_json(response)
        if plan_data:
            return _create_execution_plan(
                plan_data=plan_data,
                workspace_id=workspace_id,
                message_id=message_id,
                execution_mode=execution_mode
            )
        else:
            error_msg = "Failed to parse execution plan from LLM response"
            logger.error(error_msg)
            raise ValueError(error_msg)

    except Exception as e:
        logger.error(f"[ExecutionPlanGenerator] Failed to generate plan: {e}", exc_info=True)
        raise


def _parse_plan_json(response: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from LLM response"""
    try:
        # Try direct parse
        return json.loads(response)
    except json.JSONDecodeError:
        # Try to extract JSON from response (handle markdown code blocks)
        try:
            # Remove markdown code block markers (```json ... ```)
            cleaned = response.strip()
            if cleaned.startswith('```'):
                # Find the first newline after ```
                first_newline = cleaned.find('\n')
                if first_newline > 0:
                    cleaned = cleaned[first_newline:].strip()
                # Remove trailing ```
                if cleaned.endswith('```'):
                    cleaned = cleaned[:-3].strip()

            # Find JSON object in response
            start = cleaned.find('{')
            end = cleaned.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = cleaned[start:end]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    # Log more details about the parsing error
                    logger.warning(f"[ExecutionPlanGenerator] JSON parse error at position {e.pos}: {e.msg}")
                    logger.warning(f"[ExecutionPlanGenerator] JSON snippet around error: {json_str[max(0, e.pos-50):e.pos+50]}")
                    # Try to fix common issues: incomplete JSON (missing closing braces)
                    # This is a fallback - if JSON is incomplete, we can't reliably parse it
                    pass
        except Exception as e:
            logger.warning(f"[ExecutionPlanGenerator] Error during JSON extraction: {e}")

    logger.warning(f"[ExecutionPlanGenerator] Failed to parse JSON from response (first 500 chars): {response[:500]}")
    logger.warning(f"[ExecutionPlanGenerator] Response length: {len(response)} chars")
    return None


def _convert_steps_to_tasks(steps: List[ExecutionStep]) -> List[TaskPlan]:
    """
    Convert ExecutionStep list to TaskPlan list for execution.

    Enables the same ExecutionPlan to be used for UI display (steps) and execution (tasks).
    """
    tasks = []
    for step in steps:
        # Determine pack_id from playbook_code or tool_name
        pack_id = None
        if step.playbook_code:
            # Use playbook_code as pack_id (most playbooks map 1:1 to packs)
            pack_id = step.playbook_code
        elif step.tool_name:
            # Try to map tool_name to pack_id
            # Common mappings:
            tool_to_pack = {
                "generic_drafting": "content_drafting",
                "drafting": "content_drafting",
                "storyboard": "storyboard",
                "planning": "daily_planning",
                "research": "research",
            }
            pack_id = tool_to_pack.get(step.tool_name, step.tool_name)

        if not pack_id:
            # Skip steps without playbook or tool
            logger.warning(
                f"[ExecutionPlanGenerator] Step {step.step_id} (intent: {step.intent}) "
                f"has no playbook_code or tool_name, skipping task conversion. "
                f"This step will appear in UI but won't be executed."
            )
            print(
                f"[ExecutionPlanGenerator] WARNING: Step {step.step_id} skipped - "
                f"playbook_code={step.playbook_code}, tool_name={step.tool_name}, intent={step.intent}",
                file=sys.stderr
            )
            continue

        # Determine task_type from step intent
        task_type = "execute"  # Default task type
        if "generate" in step.intent.lower() or "create" in step.intent.lower():
            task_type = "generate_draft"
        elif "extract" in step.intent.lower() or "analyze" in step.intent.lower():
            task_type = "extract_intents"
        elif "plan" in step.intent.lower() or "schedule" in step.intent.lower():
            task_type = "generate_tasks"

        # Create TaskPlan
        task_plan = TaskPlan(
            pack_id=pack_id,
            task_type=task_type,
            params={
                "intent": step.intent,
                "reasoning": step.reasoning,
                "artifacts": step.artifacts,
                "step_id": step.step_id,
                "depends_on": step.depends_on
            },
            side_effect_level=step.side_effect_level or "readonly",
            auto_execute=not step.requires_confirmation,
            requires_cta=step.requires_confirmation
        )
        tasks.append(task_plan)
        logger.info(f"[ExecutionPlanGenerator] Converted step {step.step_id} to TaskPlan: pack_id={pack_id}, task_type={task_type}")

    return tasks


def _create_execution_plan(
    plan_data: Dict[str, Any],
    workspace_id: str,
    message_id: str,
    execution_mode: str
) -> ExecutionPlan:
    """Create ExecutionPlan from parsed JSON data"""
    steps = []
    for step_data in plan_data.get('steps', []):
        step = ExecutionStep(
            step_id=step_data.get('step_id', f"S{len(steps)+1}"),
            intent=step_data.get('intent', 'Execute task'),
            playbook_code=step_data.get('playbook_code'),
            tool_name=step_data.get('tool_name'),
            artifacts=step_data.get('artifacts', []),
            reasoning=step_data.get('reasoning'),
            depends_on=step_data.get('depends_on', []),
            requires_confirmation=step_data.get('requires_confirmation', False),
            side_effect_level=step_data.get('side_effect_level', 'readonly'),
            estimated_duration=step_data.get('estimated_duration')
        )
        steps.append(step)

    # Convert steps to tasks for execution
    tasks = _convert_steps_to_tasks(steps)
    
    logger.info(
        f"[ExecutionPlanGenerator] Created ExecutionPlan: {len(steps)} steps, {len(tasks)} tasks. "
        f"Steps with playbook_code: {sum(1 for s in steps if s.playbook_code)}, "
        f"Steps with tool_name: {sum(1 for s in steps if s.tool_name)}"
    )
    print(
        f"[ExecutionPlanGenerator] ExecutionPlan created: {len(steps)} steps -> {len(tasks)} tasks. "
        f"Missing playbook_code in {len(steps) - len(tasks)} steps.",
        file=sys.stderr
    )

    return ExecutionPlan(
        id=str(uuid.uuid4()),
        message_id=message_id,
        workspace_id=workspace_id,
        user_request_summary=plan_data.get('user_request_summary'),
        reasoning=plan_data.get('reasoning'),
        plan_summary=plan_data.get('plan_summary'),
        steps=steps,
        tasks=tasks,  # Now includes tasks for execution
        execution_mode=execution_mode,
        confidence=plan_data.get('confidence', 0.7),
        created_at=datetime.utcnow()
    )


def _create_minimal_plan(
    user_request: str,
    workspace_id: str,
    message_id: str,
    execution_mode: str,
    expected_artifacts: Optional[List[str]] = None
) -> ExecutionPlan:
    """Create minimal plan without LLM (fallback)"""
    step = ExecutionStep(
        step_id="S1",
        intent="Process user request",
        playbook_code=None,
        tool_name="generic_drafting",
        artifacts=expected_artifacts or ["md"],
        reasoning="No specific playbook matched, using generic drafting",
        depends_on=[],
        requires_confirmation=False,
        side_effect_level="soft_write"
    )

    # Convert step to task
    tasks = _convert_steps_to_tasks([step])

    return ExecutionPlan(
        id=str(uuid.uuid4()),
        message_id=message_id,
        workspace_id=workspace_id,
        user_request_summary=user_request[:100],
        reasoning="Minimal plan generated without LLM analysis",
        plan_summary="Processing request with generic drafting",
        steps=[step],
        tasks=tasks,  # Now includes tasks for execution
        execution_mode=execution_mode,
        confidence=0.5,
        created_at=datetime.utcnow()
    )


async def record_execution_plan_event(
    plan: ExecutionPlan,
    profile_id: str,
    project_id: Optional[str] = None
) -> None:
    """
    Record ExecutionPlan as EXECUTION_PLAN MindEvent

    This creates the trace for debugging, replay, and optimization.

    Args:
        plan: ExecutionPlan to record
        profile_id: User profile ID
        project_id: Optional project ID
    """
    try:
        from backend.app.models.mindscape import MindEvent, EventType, EventActor
        from backend.app.services.mindscape_store import MindscapeStore

        store = MindscapeStore()

        event = MindEvent(
            id=plan.id,  # Use plan ID as event ID for easy lookup
            timestamp=plan.created_at,
            actor=EventActor.ASSISTANT,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=plan.workspace_id,
            event_type=EventType.EXECUTION_PLAN,
            payload=plan.to_event_payload(),
            entity_ids=[],
            metadata={
                "execution_mode": plan.execution_mode,
                "step_count": len(plan.steps),
                "confidence": plan.confidence
            }
        )

        store.create_event(event, generate_embedding=True)
        logger.info(f"[ExecutionPlanGenerator] Recorded EXECUTION_PLAN event: {plan.id}")

    except Exception as e:
        logger.warning(f"[ExecutionPlanGenerator] Failed to record plan event: {e}")

