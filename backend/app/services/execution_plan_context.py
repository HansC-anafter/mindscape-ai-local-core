"""Context, prompt, and chat helpers for execution plan generation."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def _coerce_chat_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return str(response.get("content") or response.get("text") or "")
    return str(response or "")


def _resolve_governed_chat_inputs(llm_provider: Any) -> tuple[Any, Any]:
    provider = llm_provider if hasattr(llm_provider, "chat_completion") else None
    llm_provider_manager = (
        llm_provider
        if hasattr(llm_provider, "get_llm_manager")
        and hasattr(llm_provider, "get_llm_provider")
        else None
    )

    if provider is None and llm_provider_manager is None:
        from backend.app.services.config_store import ConfigStore
        from backend.app.services.playbook.llm_provider_manager import (
            PlaybookLLMProviderManager,
        )

        llm_provider_manager = PlaybookLLMProviderManager(ConfigStore())

    return provider, llm_provider_manager


EXECUTION_PLAN_PROMPT = """You are an Execution Planning Agent. Your task is to analyze the user's request
and create a structured execution plan BEFORE taking any action.

{project_context}
{context_section}

## User Request
{user_request}

{uploaded_files_context}

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


def format_playbooks_prompt(
    playbooks_to_use: Optional[List[Dict[str, Any]]],
) -> tuple[str, List[str]]:
    playbooks_str = "None available"
    playbook_codes_list: List[str] = []
    if not playbooks_to_use:
        return playbooks_str, playbook_codes_list

    playbooks_list = []
    for pb in playbooks_to_use:
        code = pb.get("playbook_code", pb.get("code", "unknown"))
        name = pb.get("name", code)
        desc = pb.get("description", "")[:100]
        outputs = pb.get("output_types", [])
        playbooks_list.append(f"- {code}: {name} (outputs: {outputs}) - {desc}")
        if code and code != "unknown":
            playbook_codes_list.append(code)
    playbooks_str = "\n".join(playbooks_list) if playbooks_list else "None available"

    if playbook_codes_list:
        playbooks_str += (
            "\n\n## Valid Playbook Codes (use EXACTLY these codes, case-sensitive):\n"
            + ", ".join(sorted(playbook_codes_list))
        )

    return playbooks_str, playbook_codes_list


async def build_project_context(
    project_id: Optional[str],
    project_assignment_decision: Optional[Dict[str, Any]],
    workspace_id: str,
) -> str:
    if not project_id or not project_assignment_decision:
        return ""

    try:
        from backend.app.services.mindscape_store import MindscapeStore
        from backend.app.services.project.project_manager import ProjectManager

        store = MindscapeStore()
        project_manager = ProjectManager(store)
        project = await project_manager.get_project(project_id, workspace_id=workspace_id)

        if not project:
            return ""

        recent_phases_str = ""
        try:
            from backend.app.services.project.project_phase_manager import (
                ProjectPhaseManager,
            )

            phase_manager = ProjectPhaseManager(store=store)
            recent_phases = await phase_manager.get_recent_phases(
                project_id=project_id, limit=3
            )
            if recent_phases:
                phase_lines = [
                    f"  {i+1}. Phase {p.kind}: {p.summary[:80]}"
                    for i, p in enumerate(recent_phases)
                ]
                recent_phases_str = (
                    "\n- Related previous phases:\n" + "\n".join(phase_lines)
                )
        except Exception as exc:
            logger.debug(f"Failed to load recent phases for project {project_id}: {exc}")

        assignment_relation = project_assignment_decision.get("relation", "unknown")
        confidence = project_assignment_decision.get("confidence", 0.0)
        reasoning = project_assignment_decision.get("reasoning", "N/A")

        return f"""
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
    except Exception as exc:
        logger.warning(f"Failed to build project context: {exc}")
        return ""


def build_context_section(planning_context: Optional[str]) -> str:
    if not planning_context:
        return ""
    return f"""
## Thread & Workspace Context (Thread-First)
{planning_context}
"""


def append_execution_plan_trace(
    workspace_id: str,
    user_request: str,
    playbooks_to_use: Optional[List[Dict[str, Any]]],
    effective_playbooks: Optional[List[Dict[str, Any]]],
    available_playbooks: Optional[List[Dict[str, Any]]],
) -> None:
    try:
        log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"\n==== EXECUTION PLAN GENERATOR TRACE {_utc_now()} ====\n")
            handle.write(f"Workspace: {workspace_id}\n")
            handle.write(f"Message: {user_request}\n")
            handle.write(
                f"Playbooks to use count: {len(playbooks_to_use) if playbooks_to_use else 0}\n"
            )
            handle.write(
                f"effective_playbooks count: {len(effective_playbooks) if effective_playbooks else 'None'}\n"
            )
            handle.write(
                f"available_playbooks count: {len(available_playbooks) if available_playbooks else 'None'}\n"
            )
            if playbooks_to_use:
                for playbook in playbooks_to_use:
                    code = playbook.get("playbook_code", playbook.get("code", ""))
                    if "ig_analyze_following" in str(code):
                        handle.write("[TRACE] ig_analyze_following in playbooks_to_use:\n")
                        handle.write(
                            f"  code: {playbook.get('playbook_code', playbook.get('code', 'N/A'))}\n"
                        )
                        handle.write(f"  name: {playbook.get('name', 'N/A')}\n")
                        description = playbook.get("description")
                        handle.write(
                            f"  description: {description[:100] if description else '(EMPTY)'}\n"
                        )
            handle.write("==========================================\n")
    except Exception:
        pass


def append_plan_prompt_evidence(
    workspace_id: str,
    playbooks_to_use: Optional[List[Dict[str, Any]]],
    prompt: str,
) -> None:
    try:
        log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"\n==== PLAN EVIDENCE {_utc_now()} ====\n")
            handle.write(f"Workspace: {workspace_id}\n")
            handle.write(
                f"Playbooks to use: {len(playbooks_to_use) if playbooks_to_use else 0}\n"
            )
            handle.write(f"Prompt (User Side):\n{prompt}\n")
            handle.write("==========================================\n")
    except Exception:
        pass


def append_plan_response(response_text: str) -> None:
    try:
        log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"\n==== PLAN RESPONSE {_utc_now()} ====\n")
            handle.write(f"Response:\n{response_text}\n")
            handle.write("==========================================\n")
    except Exception:
        pass


def append_plan_exception(exc: Exception) -> None:
    try:
        log_path = os.path.join(os.getcwd(), "data/mindscape_evidence.log")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"\n==== PLAN EXCEPTION {_utc_now()} ====\n")
            handle.write(f"Error: {str(exc)}\n")
            handle.write("==========================================\n")
    except Exception:
        pass
