"""Work-scene suggestion flow for the agent runner facade."""

import json
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List

logger = logging.getLogger(__name__)


def get_work_scenes() -> List[Dict[str, Any]]:
    """Return the v0 work-scene catalog."""
    return [
        {
            "id": "daily_planning",
            "name": "每日整理 & 優先級",
            "description": "整理每日/每週任務，排優先順序",
            "agent_type": "planner",
        },
        {
            "id": "project_breakdown",
            "name": "專案拆解 & 里程碑",
            "description": "將專案拆成階段和里程碑",
            "agent_type": "planner",
        },
        {
            "id": "content_drafting",
            "name": "內容／文案起稿",
            "description": "起草文案、文章、貼文",
            "agent_type": "writer",
        },
        {
            "id": "learning_plan",
            "name": "學習計畫 & 筆記整理",
            "description": "整理內容重點，制定學習計畫",
            "agent_type": "planner",
        },
        {
            "id": "mindful_dialogue",
            "name": "心智 / 情緒整理對話",
            "description": "梳理焦慮，用提問方式釐清狀態",
            "agent_type": "coach",
        },
        {
            "id": "client_collaboration",
            "name": "客戶／合作案梳理",
            "description": "整理客戶/合作案現況，列出選項",
            "agent_type": "planner",
        },
    ]


async def suggest_work_scene(
    *,
    profile_id: str,
    task: str,
    llm_provider: Any,
    build_prompt_func: Callable[..., Any],
    call_llm_func: Callable[..., Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Use LLM to suggest the best work scene for a given task."""
    if not task:
        raise ValueError("Task description required")

    work_scenes = get_work_scenes()
    scenes_text = "\n".join(
        [
            f"- {scene['id']}: {scene['name']} - {scene['description']} (適合: {scene['agent_type']})"
            for scene in work_scenes
        ]
    )

    system_prompt = f"""You are a helpful assistant that suggests the best work scenario for a user's task.

Available work scenarios:
{scenes_text}

Analyze the user's task and suggest the most appropriate work scenario.
Respond in JSON format:
{{
    "suggested_scene_id": "scene_id",
    "confidence": 0.0-1.0,
    "reason": "brief explanation in Traditional Chinese"
}}"""

    user_prompt = (
        f"Task: {task}\n\nWhich work scenario is most suitable for this task?"
    )

    try:
        messages = build_prompt_func(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        response_dict = await call_llm_func(
            messages=messages,
            llm_provider=llm_provider,
            temperature=0.3,
            max_tokens=400,
            purpose="agent_runner_work_scene_suggestion",
            stage_name="scope_decision",
            risk_level="read",
        )
        response_text = response_dict.get("text", "")

        json_match = re.search(r"\{[^{}]*\}", response_text, re.DOTALL)
        if json_match:
            suggestion_data = json.loads(json_match.group())
        else:
            suggestion_data = json.loads(response_text)

        suggested_id = suggestion_data.get("suggested_scene_id", work_scenes[0]["id"])
        scene_info = next(
            (scene for scene in work_scenes if scene["id"] == suggested_id),
            work_scenes[0],
        )

        return {
            "suggested_scene_id": suggested_id,
            "suggested_scene": scene_info,
            "confidence": suggestion_data.get("confidence", 0.7),
            "reason": suggestion_data.get("reason", "根據任務內容自動推薦"),
            "all_scenes": work_scenes,
        }

    except Exception as exc:
        logger.error("Scene suggestion failed: %s", exc)
        return {
            "suggested_scene_id": work_scenes[0]["id"],
            "suggested_scene": work_scenes[0],
            "confidence": 0.5,
            "reason": "自動推薦失敗，使用預設場景",
            "all_scenes": work_scenes,
        }
