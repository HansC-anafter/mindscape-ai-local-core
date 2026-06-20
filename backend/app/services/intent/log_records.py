"""
Intent log recording, replay, and evaluation helpers.
"""

from datetime import datetime
from typing import Any, Dict, Optional
import uuid

from backend.app.models.mindscape import IntentLog

from .models import IntentAnalysisResult


def log_intent_decision(
    store: Any,
    llm_provider: Any,
    result: IntentAnalysisResult,
) -> None:
    """
    Store an intent decision for offline optimization.

    Args:
        store: MindscapeStore-compatible object
        llm_provider: LLM provider currently attached to the pipeline
        result: IntentAnalysisResult to log
    """
    intent_log = IntentLog(
        id=str(uuid.uuid4()),
        timestamp=result.timestamp,
        raw_input=result.raw_input,
        channel=result.channel,
        profile_id=result.profile_id,
        project_id=result.project_id,
        workspace_id=result.workspace_id,
        pipeline_steps=result.pipeline_steps,
        final_decision={
            "interaction_type": (
                result.interaction_type.value if result.interaction_type else None
            ),
            "interaction_confidence": result.interaction_confidence,
            "task_domain": result.task_domain.value if result.task_domain else None,
            "task_domain_confidence": result.task_domain_confidence,
            "selected_playbook_code": result.selected_playbook_code,
            "playbook_confidence": result.playbook_confidence,
            "playbook_context": result.playbook_context,
        },
        user_override=None,
        metadata={
            "llm_provider": (
                llm_provider.__class__.__name__ if llm_provider else None
            )
        },
    )

    store.create_intent_log(intent_log)


async def replay_intent_log(
    store: Any,
    pipeline_factory: Any,
    log_id: str,
    llm_provider: Any = None,
    use_llm: bool = True,
    rule_priority: bool = True,
) -> IntentAnalysisResult:
    """
    Replay an intent log with new settings.

    Args:
        store: MindscapeStore-compatible object
        pipeline_factory: IntentPipeline class or compatible factory
        log_id: Intent log ID to replay
        llm_provider: Optional new LLM provider
        use_llm: Optional new use_llm setting
        rule_priority: Optional new rule_priority setting

    Returns:
        New IntentAnalysisResult from replay.
    """
    original_log = store.get_intent_log(log_id)
    if not original_log:
        raise ValueError(f"Intent log not found: {log_id}")

    temp_pipeline = pipeline_factory(
        llm_provider=llm_provider,
        use_llm=use_llm,
        rule_priority=rule_priority,
        store=None,
        enable_logging=False,
    )

    return await temp_pipeline.analyze(
        user_input=original_log.raw_input,
        profile_id=original_log.profile_id,
        channel=original_log.channel,
    )


def evaluate_intent_logs(
    store: Any,
    profile_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Evaluate intent logs and calculate metrics.

    Args:
        store: MindscapeStore-compatible object
        profile_id: Optional profile filter
        start_time: Optional start time filter
        end_time: Optional end time filter

    Returns:
        Evaluation metrics dictionary.
    """
    annotated_logs = store.list_intent_logs(
        profile_id=profile_id,
        start_time=start_time,
        end_time=end_time,
        has_override=True,
        limit=1000,
    )

    if not annotated_logs:
        return {
            "total_logs": 0,
            "annotated_logs": 0,
            "accuracy": None,
            "layer1_accuracy": None,
            "layer2_accuracy": None,
            "layer3_accuracy": None,
            "confusion_matrix": {},
        }

    total = len(annotated_logs)
    correct_layer1 = 0
    correct_layer2 = 0
    correct_layer3 = 0
    correct_overall = 0

    confusion_matrix = {"interaction_type": {}, "task_domain": {}, "playbook": {}}

    for log in annotated_logs:
        final = log.final_decision
        override = log.user_override

        if override.get("correct_interaction_type"):
            expected = override["correct_interaction_type"]
            actual = final.get("interaction_type")
            if expected == actual:
                correct_layer1 += 1
            key = f"{actual}->{expected}"
            confusion_matrix["interaction_type"][key] = (
                confusion_matrix["interaction_type"].get(key, 0) + 1
            )

        if override.get("correct_task_domain"):
            expected = override["correct_task_domain"]
            actual = final.get("task_domain")
            if expected == actual:
                correct_layer2 += 1
            key = f"{actual}->{expected}"
            confusion_matrix["task_domain"][key] = (
                confusion_matrix["task_domain"].get(key, 0) + 1
            )

        if override.get("correct_playbook_code"):
            expected = override["correct_playbook_code"]
            actual = final.get("selected_playbook_code")
            if expected == actual:
                correct_layer3 += 1
            key = f"{actual}->{expected}"
            confusion_matrix["playbook"][key] = (
                confusion_matrix["playbook"].get(key, 0) + 1
            )

        if (
            override.get("correct_interaction_type") == final.get("interaction_type")
            and override.get("correct_task_domain") == final.get("task_domain")
            and override.get("correct_playbook_code")
            == final.get("selected_playbook_code")
        ):
            correct_overall += 1

    all_logs = store.list_intent_logs(
        profile_id=profile_id,
        start_time=start_time,
        end_time=end_time,
        has_override=None,
        limit=10000,
    )

    return {
        "total_logs": len(all_logs),
        "annotated_logs": total,
        "accuracy": correct_overall / total if total > 0 else None,
        "layer1_accuracy": correct_layer1 / total if total > 0 else None,
        "layer2_accuracy": correct_layer2 / total if total > 0 else None,
        "layer3_accuracy": correct_layer3 / total if total > 0 else None,
        "confusion_matrix": confusion_matrix,
        "error_breakdown": {
            "layer1_errors": total - correct_layer1,
            "layer2_errors": total - correct_layer2,
            "layer3_errors": total - correct_layer3,
        },
    }
