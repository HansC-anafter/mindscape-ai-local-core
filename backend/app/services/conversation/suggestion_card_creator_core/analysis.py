"""LLM analysis helpers for suggestion card creation."""

from typing import Any, Dict, Optional

BACKGROUND_PLAYBOOKS = {"habit_learning"}


def is_background_playbook(playbook_code: Optional[str]) -> bool:
    if not playbook_code:
        return False
    return playbook_code.lower() in BACKGROUND_PLAYBOOKS


def extract_playbook_llm_analysis(playbook_context: Dict[str, Any]) -> Dict[str, Any]:
    llm_analysis = playbook_context.get("llm_analysis", {})
    if not llm_analysis and isinstance(playbook_context.get("context"), dict):
        llm_analysis = playbook_context.get("context", {}).get("llm_analysis", {})
    return llm_analysis


def prepare_llm_analysis(task_plan) -> Dict[str, Any]:
    llm_analysis = task_plan.params.get("llm_analysis", {}) if task_plan.params else {}
    return normalize_llm_analysis(
        llm_analysis,
        is_background_playbook(getattr(task_plan, "pack_id", None)),
    )


def normalize_llm_analysis(
    llm_analysis: Dict[str, Any], is_background_playbook_value: bool
) -> Dict[str, Any]:
    if not llm_analysis or not isinstance(llm_analysis, dict):
        llm_analysis = {}

    if "confidence" not in llm_analysis:
        llm_analysis["confidence"] = 0.0

    if "reason" not in llm_analysis:
        if is_background_playbook_value:
            llm_analysis["reason"] = (
                "This task will be executed automatically in the background, "
                "no LLM analysis needed"
            )
        else:
            llm_analysis["reason"] = ""

    if "content_tags" not in llm_analysis:
        llm_analysis["content_tags"] = []

    if "analysis_summary" not in llm_analysis:
        if is_background_playbook_value:
            llm_analysis["analysis_summary"] = "Background auto-execution task"
        else:
            llm_analysis["analysis_summary"] = ""

    if is_background_playbook_value:
        llm_analysis["is_background"] = True

    return llm_analysis
