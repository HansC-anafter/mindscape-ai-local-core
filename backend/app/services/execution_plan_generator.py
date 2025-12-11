"""
Execution Plan Generator

Generates structured ExecutionPlan (Chain-of-Thought) from user requests.
This is the "think before act" component of Execution Mode.

The generated plan:
1. Shows what the LLM decided to do
2. Provides reasoning for each step
3. Lists expected artifacts
4. Can be recorded as EXECUTION_PLAN MindEvent for traceability

See: docs-internal/architecture/workspace-llm-agent-execution-mode.md
"""

import json
import logging
import sys
import uuid
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

from backend.app.models.workspace import ExecutionPlan, ExecutionStep, TaskPlan

logger = logging.getLogger(__name__)

# Prompt template for generating execution plan
EXECUTION_PLAN_PROMPT = """You are an Execution Planning Agent. Your task is to analyze the user's request
and create a structured execution plan BEFORE taking any action.

{project_context}

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
2. **CRITICAL: playbook_code MUST be one of the playbook codes listed in "Available Playbooks" above, or null if no playbook matches**
3. **DO NOT invent new playbook codes. Only use playbook codes from the available list.**
4. If no playbook matches, use tool_name instead (e.g., "generic_drafting") or set playbook_code to null
5. List expected artifacts for each step
6. Mark steps that need user confirmation (soft_write, external_write)
7. Set realistic confidence (lower if request is ambiguous)

## Important Constraints
- playbook_code must be EXACTLY one of the codes from "Available Playbooks" (case-sensitive)
- If you cannot find a suitable playbook, set playbook_code to null and use tool_name
- Never create new playbook codes that are not in the available list

Return ONLY valid JSON, no markdown fences or explanation.
"""


async def generate_execution_plan(
    user_request: str,
    workspace_id: str,
    message_id: str,
    execution_mode: str = "execution",
    expected_artifacts: Optional[List[str]] = None,
    available_playbooks: Optional[List[Dict[str, Any]]] = None,
    effective_playbooks: Optional[List[Dict[str, Any]]] = None,
    llm_provider: Any = None,
    model_name: Optional[str] = None,
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    project_id: Optional[str] = None,
    project_assignment_decision: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
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
        available_playbooks: List of available playbooks (deprecated, kept for backward compatibility)
        effective_playbooks: Pre-resolved effective playbooks from PlaybookScopeResolver
        llm_provider: LLM provider instance
        model_name: Model to use
        progress_callback: Optional callback for progress updates (e.g., re-evaluation status)
        project_id: Optional project ID for project context
        project_assignment_decision: Optional project assignment decision metadata
        tenant_id: Tenant ID (for multi-tenant)
        user_id: Current user ID

    Returns:
        ExecutionPlan or None if generation fails
    """
    # For QA mode, skip plan generation
    if execution_mode == "qa":
        logger.info("[ExecutionPlanGenerator] Skipping plan generation for QA mode")
        return None

    if not model_name:
        error_msg = "Cannot generate execution plan: model_name is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not llm_provider:
        error_msg = "Cannot generate execution plan: llm_provider is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Use effective_playbooks if provided, fallback to available_playbooks for backward compatibility
    playbooks_to_use = effective_playbooks if effective_playbooks is not None else available_playbooks

    playbooks_str = "None available"
    playbook_codes_list = []
    if playbooks_to_use:
        playbooks_list = []
        for pb in playbooks_to_use:
            code = pb.get('playbook_code', pb.get('code', 'unknown'))
            name = pb.get('name', code)
            desc = pb.get('description', '')[:100]
            outputs = pb.get('output_types', [])
            playbooks_list.append(f"- {code}: {name} (outputs: {outputs}) - {desc}")
            if code and code != 'unknown':
                playbook_codes_list.append(code)
        playbooks_str = "\n".join(playbooks_list) if playbooks_list else "None available"

        if playbook_codes_list:
            playbooks_str += f"\n\n## Valid Playbook Codes (use EXACTLY these codes, case-sensitive):\n" + ", ".join(sorted(playbook_codes_list))

    project_context_str = ""
    if project_id and project_assignment_decision:
        try:
            from backend.app.services.project.project_manager import ProjectManager
            from backend.app.services.mindscape_store import MindscapeStore

            store = MindscapeStore()
            project_manager = ProjectManager(store)
            project = await project_manager.get_project(project_id, workspace_id=workspace_id)

            if project:
                recent_phases_str = ""
                try:
                    from backend.app.services.project.project_phase_manager import ProjectPhaseManager
                    phase_manager = ProjectPhaseManager(store=store)
                    recent_phases = await phase_manager.get_recent_phases(project_id=project_id, limit=3)
                    if recent_phases:
                        phase_lines = [f"  {i+1}. Phase {p.kind}: {p.summary[:80]}" for i, p in enumerate(recent_phases)]
                        recent_phases_str = "\n- Related previous phases:\n" + "\n".join(phase_lines)
                except Exception as e:
                    logger.debug(f"Failed to load recent phases for project {project_id}: {e}")

                assignment_relation = project_assignment_decision.get('relation', 'unknown')
                confidence = project_assignment_decision.get('confidence', 0.0)
                reasoning = project_assignment_decision.get('reasoning', 'N/A')

                project_context_str = f"""
[PROJECT CONTEXT]

- Active project_id: {project_id}
- Project title: 「{project.title}」
- Project type: {project.type}
- Project summary: {project.metadata.get('summary', 'N/A') if project.metadata else 'N/A'}
- This message is classified as: 「{assignment_relation}」, confidence = {confidence:.2f}
- Reasoning: {reasoning}
{recent_phases_str}

IMPORTANT: When interpreting the user's request, treat it as a continuation of the above Project, unless the user explicitly states they want to start a completely different work item.
"""
        except Exception as e:
            logger.warning(f"Failed to build project context: {e}")

    prompt = EXECUTION_PLAN_PROMPT.format(
        project_context=project_context_str,
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

        plan_data = _parse_plan_json(response)
        if not plan_data:
            error_msg = "Failed to parse execution plan from LLM response"
            logger.error(error_msg)
            raise ValueError(error_msg)

        plan_data = await _validate_and_reevaluate_plan(
            plan_data=plan_data,
            available_playbooks=available_playbooks,
            user_request=user_request,
            execution_mode=execution_mode,
            expected_artifacts=expected_artifacts,
            llm_provider=llm_provider,
            model_name=model_name,
            progress_callback=progress_callback
        )

        execution_plan = _create_execution_plan(
            plan_data=plan_data,
            workspace_id=workspace_id,
            message_id=message_id,
            execution_mode=execution_mode,
            available_playbooks=available_playbooks
        )

        if project_id:
            execution_plan.project_id = project_id
        if project_assignment_decision:
            execution_plan.project_assignment_decision = project_assignment_decision

        return execution_plan

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


async def _validate_and_reevaluate_plan(
    plan_data: Dict[str, Any],
    available_playbooks: Optional[List[Dict[str, Any]]],
    user_request: str,
    execution_mode: str,
    expected_artifacts: Optional[List[str]],
    llm_provider: Any,
    model_name: str,
    progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
) -> Dict[str, Any]:
    """
    Validate playbook codes and re-evaluate if invalid codes are found.

    If LLM generated invalid playbook codes, ask it to re-evaluate and choose
    from available playbooks.
    """
    if not available_playbooks:
        return plan_data

    valid_playbook_codes = set()
    playbook_code_to_info = {}
    for pb in available_playbooks:
        code = pb.get('playbook_code', pb.get('code', ''))
        if code:
            valid_playbook_codes.add(code.lower())
            playbook_code_to_info[code.lower()] = {
                'code': code,
                'name': pb.get('name', code),
                'description': pb.get('description', '')[:100]
            }

    # Special packs that are always valid
    special_packs = {"intent_extraction", "semantic_seeds"}

    invalid_steps = []
    steps = plan_data.get('steps', [])

    for i, step in enumerate(steps):
        playbook_code = step.get('playbook_code')
        if playbook_code:
            playbook_code_lower = playbook_code.lower()
            is_valid = (
                playbook_code_lower in valid_playbook_codes or
                playbook_code_lower in special_packs
            )

            if not is_valid:
                invalid_steps.append({
                    'index': i,
                    'step_id': step.get('step_id', f'S{i+1}'),
                    'intent': step.get('intent', ''),
                    'invalid_playbook_code': playbook_code,
                    'reasoning': step.get('reasoning', '')
                })

    # If no invalid codes, return original plan
    if not invalid_steps:
        return plan_data

    logger.warning(
        f"[ExecutionPlanGenerator] Found {len(invalid_steps)} steps with invalid playbook codes. "
        f"Re-evaluating with LLM..."
    )
    print(
        f"[ExecutionPlanGenerator] WARNING: Found {len(invalid_steps)} invalid playbook codes, re-evaluating...",
        file=sys.stderr
    )

    # Notify user about re-evaluation
    if progress_callback:
        invalid_codes = [s['invalid_playbook_code'] for s in invalid_steps]
        progress_callback('reevaluation_started', {
            'message_key': 'execution_plan.reevaluation_started',
            'message_params': {
                'count': len(invalid_steps)
            },
            'invalid_codes': invalid_codes,
            'invalid_steps': [
                {
                    'step_id': s['step_id'],
                    'intent': s['intent'],
                    'invalid_code': s['invalid_playbook_code']
                }
                for s in invalid_steps
            ],
            'available_playbook_count': len(available_playbooks) if available_playbooks else 0
        })

    valid_codes_list = sorted([info['code'] for info in playbook_code_to_info.values()])

    reevaluation_prompt = f"""You previously generated an execution plan, but some steps used invalid playbook codes that are not in the available list.

## Invalid Playbook Codes Found:
{chr(10).join([f"- Step {s['step_id']} (intent: {s['intent']}): '{s['invalid_playbook_code']}' - {s['reasoning']}" for s in invalid_steps])}

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
            user_prompt=reevaluation_prompt
        )

        provider_name = None
        if "gemini" in model_name.lower():
            provider_name = "vertex-ai"
        elif "gpt" in model_name.lower() or "o1" in model_name.lower() or "o3" in model_name.lower():
            provider_name = "openai"
        elif "claude" in model_name.lower():
            provider_name = "anthropic"

        if provider_name:
            provider = llm_provider.get_provider(provider_name)
            if provider and hasattr(provider, 'chat_completion'):
                response = await provider.chat_completion(
                    messages=messages,
                    model=model_name,
                    temperature=0.2,  # Lower temperature for corrections
                    max_tokens=4000
                )

                corrected_plan_data = _parse_plan_json(response)
                if corrected_plan_data:
                    logger.info(f"[ExecutionPlanGenerator] Successfully re-evaluated plan, corrected {len(invalid_steps)} invalid playbook codes")
                    print(f"[ExecutionPlanGenerator] Successfully corrected {len(invalid_steps)} invalid playbook codes", file=sys.stderr)

                    # Notify user about successful correction
                    if progress_callback:
                        progress_callback('reevaluation_completed', {
                            'message_key': 'execution_plan.reevaluation_completed',
                            'message_params': {
                                'count': len(invalid_steps)
                            },
                            'corrected_count': len(invalid_steps)
                        })

                    return corrected_plan_data
                else:
                    logger.warning(f"[ExecutionPlanGenerator] Failed to parse re-evaluation response, using original plan with filtered steps")
    except Exception as e:
        logger.warning(f"[ExecutionPlanGenerator] Re-evaluation failed: {e}, using original plan with filtered steps", exc_info=True)

    logger.info(f"[ExecutionPlanGenerator] Removing {len(invalid_steps)} steps with invalid playbook codes")
    valid_steps = [step for i, step in enumerate(steps) if i not in [s['index'] for s in invalid_steps]]
    plan_data['steps'] = valid_steps

    return plan_data


def _convert_steps_to_tasks(
    steps: List[ExecutionStep],
    plan_confidence: float = 0.7,
    available_playbooks: Optional[List[Dict[str, Any]]] = None
) -> List[TaskPlan]:
    """
    Convert ExecutionStep list to TaskPlan list for execution.

    Enables the same ExecutionPlan to be used for UI display (steps) and execution (tasks).

    Args:
        steps: List of ExecutionStep from LLM
        plan_confidence: Confidence score from plan
        available_playbooks: List of available playbooks to validate against
    """
    valid_playbook_codes = set()
    if available_playbooks:
        for pb in available_playbooks:
            code = pb.get('playbook_code', pb.get('code', ''))
            if code:
                valid_playbook_codes.add(code.lower())

    # Special packs that are always valid (even if not in playbook list)
    special_packs = {"intent_extraction", "semantic_seeds"}

    tasks = []
    for step in steps:
        pack_id = None
        if step.playbook_code:
            playbook_code_lower = step.playbook_code.lower()
            is_valid = (
                playbook_code_lower in valid_playbook_codes or
                playbook_code_lower in special_packs
            )

            if not is_valid:
                logger.warning(
                    f"[ExecutionPlanGenerator] Step {step.step_id} (intent: {step.intent}) "
                    f"has invalid playbook_code '{step.playbook_code}' not in available playbooks. "
                    f"Skipping task conversion. This step will appear in UI but won't be executed."
                )
                print(
                    f"[ExecutionPlanGenerator] WARNING: Step {step.step_id} skipped - "
                    f"invalid playbook_code='{step.playbook_code}' not in playbook list, intent={step.intent}",
                    file=sys.stderr
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
                f"has no playbook_code or tool_name, skipping task conversion. "
                f"This step will appear in UI but won't be executed."
            )
            print(
                f"[ExecutionPlanGenerator] WARNING: Step {step.step_id} skipped - "
                f"playbook_code={step.playbook_code}, tool_name={step.tool_name}, intent={step.intent}",
                file=sys.stderr
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
                "llm_analysis": {
                    "confidence": plan_confidence
                }
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
    execution_mode: str,
    available_playbooks: Optional[List[Dict[str, Any]]] = None
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

    plan_confidence = plan_data.get('confidence', 0.7)
    tasks = _convert_steps_to_tasks(steps, plan_confidence=plan_confidence, available_playbooks=available_playbooks)

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
        created_at=datetime.utcnow(),
        project_id=None,  # Will be set by caller if needed
        project_assignment_decision=None  # Will be set by caller if needed
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

    tasks = _convert_steps_to_tasks([step], plan_confidence=0.5)

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

