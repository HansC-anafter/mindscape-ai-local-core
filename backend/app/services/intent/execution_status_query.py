"""
Execution-status query helpers for IntentPipeline.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import MindscapeProfile
from backend.app.models.playbook import (
    HandoffPlan,
    InteractionMode,
    PlaybookKind,
    WorkflowStep,
)
from backend.app.shared.llm_utils import build_prompt, call_llm

from .utils import parse_json_from_response

logger = logging.getLogger(__name__)


async def check_execution_status_query(
    user_input: str,
    workspace_id: str,
    llm_provider: Any,
    profile: Optional[MindscapeProfile] = None,
) -> Optional[Dict[str, Any]]:
    """
    Check whether the user is asking about execution status or progress.

    Args:
        user_input: User input text
        workspace_id: Workspace ID used for task lookup
        llm_provider: LLM provider used for progress-query judgment
        profile: Optional profile context retained for compatibility

    Returns:
        Dict with handoff_plan and response_suggestion if detected, otherwise None.
    """
    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()

    pending_tasks = tasks_store.list_pending_tasks(workspace_id)
    running_tasks = tasks_store.list_running_tasks(workspace_id)
    has_active_tasks = len(pending_tasks) > 0 or len(running_tasks) > 0

    progress_keywords = [
        "進度",
        "狀態",
        "執行到哪裡",
        "完成了嗎",
        "卡住了嗎",
        "progress",
        "status",
        "how far",
        "completed",
        "stuck",
        "剛剛那個",
        "出檔那個",
        "SEO 那幾個",
    ]

    message_lower = user_input.lower()
    has_progress_keyword = any(keyword in message_lower for keyword in progress_keywords)

    if not has_progress_keyword:
        return None

    if not has_active_tasks:
        if not llm_provider:
            return None

        current_tasks_snapshot = "目前沒有執行中的任務"
        llm_prompt = f"""
判斷用戶是否在詢問任務進度或執行狀態。

用戶訊息：{user_input}
當前任務快照：{current_tasks_snapshot}

請判斷：用戶是否在詢問某個任務的進度？
如果用戶在問「產品狀態」「發展狀態」等非執行任務的狀態，應該返回 false。
"""

        try:
            full_prompt = llm_prompt + '\n\nReturn JSON: {"is_progress_query": true/false}'
            messages = build_prompt(full_prompt)
            response_dict = await call_llm(
                messages=messages,
                llm_provider=llm_provider,
                model=None,
            )

            response_text = response_dict.get("text", "")
            result = parse_json_from_response(response_text)
            if result and result.get("is_progress_query"):
                available_playbooks = "筆記組織、IG 貼文生成、PDF OCR 處理等"
                return {
                    "confidence": 0.9,
                    "response_suggestion": (
                        f"目前這個工作區沒有正在執行的任務。\n"
                        f"你可以先讓我幫你啟動某個 Playbook，例如：{available_playbooks}"
                    ),
                    "handoff_plan": None,
                }
        except Exception as e:
            logger.warning(
                "Failed to check execution status query with no active tasks: %s",
                e,
                exc_info=True,
            )

    if has_active_tasks:
        current_tasks_snapshot = build_current_tasks_snapshot(pending_tasks, running_tasks)

        if not llm_provider:
            return None

        llm_prompt = f"""
判斷用戶是否在詢問任務進度或執行狀態。

用戶訊息：{user_input}
當前任務快照：
{current_tasks_snapshot}

請判斷：
1. 用戶是否在詢問某個任務的進度？
2. 是否有明確的任務可以對應？

如果用戶在問「產品狀態」「發展狀態」等非執行任務的狀態，應該返回 false。
"""

        try:
            full_prompt = (
                llm_prompt
                + '\n\nReturn JSON: {"is_progress_query": true/false, "confidence": 0.0-1.0}'
            )
            messages = build_prompt(full_prompt)
            response_dict = await call_llm(
                messages=messages,
                llm_provider=llm_provider,
                model=None,
            )

            response_text = response_dict.get("text", "")
            result = parse_json_from_response(response_text)
            if result and result.get("is_progress_query"):
                confidence = float(result.get("confidence", 0.8))

                workflow_step = WorkflowStep(
                    playbook_code="execution_status_query",
                    kind=PlaybookKind.QUERY,
                    inputs={
                        "user_message": user_input,
                        "workspace_id": workspace_id,
                        "conversation_context": "",
                    },
                    interaction_mode=InteractionMode.AUTOMATED,
                )

                handoff_plan = HandoffPlan(
                    steps=[workflow_step],
                    context={
                        "user_message": user_input,
                        "workspace_id": workspace_id,
                    },
                )

                return {
                    "confidence": confidence,
                    "handoff_plan": handoff_plan,
                    "response_suggestion": None,
                }
        except Exception as e:
            logger.warning("Failed to check execution status query: %s", e)

    return None


def build_current_tasks_snapshot(
    pending_tasks: List[Any], running_tasks: List[Any]
) -> str:
    """
    Build the current task snapshot used for LLM progress-query judgment.

    Args:
        pending_tasks: Pending tasks for the workspace
        running_tasks: Running tasks for the workspace

    Returns:
        Prompt-ready task snapshot capped to ten tasks.
    """
    snapshot = []
    for task in (running_tasks + pending_tasks)[:10]:
        snapshot.append(
            f"- {task.pack_id} ({task.status.value}): created at {task.created_at}"
        )
    return "\n".join(snapshot) if snapshot else "目前沒有執行中的任務"
