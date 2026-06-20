"""Reply summary helpers for cloud messaging."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def generate_reply_summary(
    reply_text: str,
    *,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
) -> str:
    """Generate a concise summary for rich-card display."""
    if len(reply_text) <= 100:
        return reply_text

    try:
        from backend.app.services.config_store import ConfigStore
        from backend.app.services.llm.workspace_routed_chat import (
            chat_completion_with_workspace_route,
        )
        from backend.app.services.playbook.llm_provider_manager import (
            PlaybookLLMProviderManager,
        )
        from backend.app.shared.llm_utils import build_prompt

        messages = build_prompt(
            user_prompt=(
                "Summarize the following AI response in one sentence, "
                "max 80 characters. Use the same language as the "
                "original text. Output ONLY the summary, nothing else."
                f"\n\n{reply_text[:2000]}"
            )
        )
        result = await chat_completion_with_workspace_route(
            messages=messages,
            workspace_id=workspace_id,
            profile_id=profile_id or "default-user",
            llm_provider_manager=PlaybookLLMProviderManager(ConfigStore()),
            purpose="cloud_connector_reply_summary",
            stage_name="response_formatting",
            risk_level="read",
            max_tokens=60,
            temperature=0.3,
        )
        summary = ""
        if isinstance(result, str):
            summary = result.strip()
        elif isinstance(result, dict):
            summary = str(result.get("content") or result.get("text") or "").strip()

        if summary and len(summary) <= 100:
            logger.info(
                f"[MessagingHandler] Governed summary generated: "
                f"{len(summary)} chars"
            )
            return summary

    except Exception as llm_err:
        logger.warning(
            f"[MessagingHandler] LLM summary failed, using truncation: "
            f"{llm_err}"
        )

    return truncate_at_boundary(reply_text, max_len=100)


def truncate_at_boundary(text: str, max_len: int = 100) -> str:
    """Truncate text at the nearest sentence boundary within max_len."""
    if len(text) <= max_len:
        return text

    segment = text[:max_len]

    for sep in ["。", "！", "？", ".", "!", "?"]:
        idx = segment.rfind(sep)
        if idx > max_len // 3:
            return segment[: idx + 1]

    space_idx = segment.rfind(" ")
    if space_idx > max_len // 3:
        return segment[:space_idx] + "..."

    return segment[: max_len - 3] + "..."


def extract_session_metadata(pipeline_result: Any) -> Dict[str, Any]:
    """Extract meeting session summary metadata for a cloud reply."""
    meta: Dict[str, Any] = {}
    if not pipeline_result:
        return meta

    if getattr(pipeline_result, "meeting_session_id", None):
        meta["session_id"] = pipeline_result.meeting_session_id

    if getattr(pipeline_result, "dispatch_result", None):
        dispatch_result = pipeline_result.dispatch_result
        meta["dispatch_summary"] = {
            "total_phases": dispatch_result.get("total", 0),
            "succeeded": dispatch_result.get("succeeded", 0),
            "failed": dispatch_result.get("failed", 0),
            "skipped": dispatch_result.get("skipped", 0),
            "workspaces_touched": list(dispatch_result.get("workspaces", [])),
        }

    if getattr(pipeline_result, "completion_status", None):
        meta["completion_status"] = pipeline_result.completion_status

    if getattr(pipeline_result, "task_ir_id", None):
        meta["task_ir_id"] = pipeline_result.task_ir_id

    return meta


def format_dispatch_summary(meta: Dict[str, Any]) -> str:
    """Format session dispatch summary for messaging display."""
    dispatch_summary = meta.get("dispatch_summary")
    if not dispatch_summary:
        return ""

    lines = ["\n\n──── 執行摘要 ────"]
    total = dispatch_summary.get("total_phases", 0)
    ok = dispatch_summary.get("succeeded", 0)
    fail = dispatch_summary.get("failed", 0)
    skip = dispatch_summary.get("skipped", 0)
    lines.append(f"📊 任務: {ok}/{total} 成功")
    if fail:
        lines.append(f"❌ 失敗: {fail}")
    if skip:
        lines.append(f"⏭️ 跳過: {skip}")
    workspaces = dispatch_summary.get("workspaces_touched", [])
    if workspaces:
        lines.append(f"🏠 工作區: {', '.join(workspaces[:3])}")
    status = meta.get("completion_status")
    if status:
        lines.append(f"📋 狀態: {status}")
    return "\n".join(lines)
