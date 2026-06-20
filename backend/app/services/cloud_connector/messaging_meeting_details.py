"""Meeting detail builders for cloud messaging result pages."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List

from .messaging_assets import (
    asset_candidate_from_model,
    clean_text,
    collect_asset_candidates,
    collect_execution_ids,
    dedupe_asset_candidates,
    format_page_assets_md,
    materialize_page_assets,
)

logger = logging.getLogger(__name__)


async def build_meeting_detail_md(
    handler: Any,
    store: Any,
    workspace_id: str,
    pipeline_result: Any,
) -> str:
    """Build Markdown with full meeting discussion, actions, and stats."""
    if not pipeline_result:
        return ""

    session_id = getattr(pipeline_result, "meeting_session_id", None)
    if not session_id:
        return ""

    try:
        events = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: store.events.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=100,
            ),
        )

        if not events:
            return ""

        sections = ["---", "## 📋 會議討論紀錄", ""]

        current_round = 0
        for evt in events:
            evt_type = evt.type if hasattr(evt, "type") else ""
            payload = evt.payload or {}

            if evt_type == "meeting_round":
                current_round = payload.get("round", current_round + 1)
                sections.append(f"### 第 {current_round} 輪")
                sections.append("")

            elif evt_type == "agent_turn":
                role = payload.get("role", "unknown")
                content = payload.get("content", "")
                role_label = {
                    "facilitator": "🎯 Facilitator",
                    "planner": "📐 Planner",
                    "critic": "🔍 Critic",
                }.get(role, role)
                if content:
                    if len(content) > 800:
                        content = content[:800] + "…"
                    sections.append(f"**{role_label}**")
                    sections.append(content)
                    sections.append("")

        action_items = [
            event
            for event in events
            if (event.type if hasattr(event, "type") else "") == "action_item"
        ]
        if action_items:
            sections.append("## ⚡ 行動項目")
            sections.append("")
            for index, action_item in enumerate(action_items, 1):
                payload = action_item.payload or {}
                intent = payload.get("intent", payload.get("description", ""))
                tool = payload.get("tool_name", payload.get("playbook_code", ""))
                line = f"{index}. {intent}"
                if tool:
                    line += f" (`{tool}`)"
                sections.append(line)
            sections.append("")

        decisions = [
            event
            for event in events
            if (event.type if hasattr(event, "type") else "") == "decision_final"
        ]
        if decisions:
            sections.append("## ✅ 決策")
            sections.append("")
            for decision in decisions:
                payload = decision.payload or {}
                sections.append(f"- {payload.get('summary', payload.get('decision', ''))}")
            sections.append("")

        quality = getattr(pipeline_result, "quality_score", None)
        if quality is not None:
            sections.append("## 📊 統計")
            sections.append("")
            sections.append(f"- 質量分數: {quality:.0%}")
            task_ir = getattr(pipeline_result, "task_ir_id", None)
            if task_ir:
                sections.append(f"- Task IR: `{task_ir}`")
            sections.append("")

        assets_md = await handler._build_meeting_assets_md(
            store, workspace_id, pipeline_result
        )
        if assets_md:
            sections.append(assets_md)

        if len(sections) <= 3:
            return ""

        return "\n".join(sections)

    except Exception as e:
        logger.warning(f"[MessagingHandler] Failed to build meeting detail: {e}")
        return ""


async def build_meeting_assets_md(
    handler: Any,
    store: Any,
    workspace_id: str,
    pipeline_result: Any,
) -> str:
    """Build a public-result-page section for meeting artifacts."""
    candidates: List[Dict[str, Any]] = []

    for attr in ("task_ir_artifacts", "artifact_assets"):
        raw_items = getattr(pipeline_result, attr, None) or []
        if isinstance(raw_items, list):
            for item in raw_items:
                candidates.extend(collect_asset_candidates(item))

    for file_path in list(getattr(pipeline_result, "artifact_file_paths", None) or []):
        candidates.append({"file_path": file_path, "title": Path(str(file_path)).name})

    artifact_ids = [
        item
        for item in list(getattr(pipeline_result, "artifact_ids", None) or [])
        if clean_text(item)
    ]
    for artifact_id in artifact_ids:
        candidates.append({"artifact_id": artifact_id, "title": artifact_id})

    dispatch_result = getattr(pipeline_result, "dispatch_result", None)
    candidates.extend(collect_asset_candidates(dispatch_result))

    artifacts_store = getattr(store, "artifacts", None)
    if artifacts_store:
        for artifact_id in artifact_ids:
            try:
                artifact = await asyncio.to_thread(
                    artifacts_store.get_artifact, artifact_id
                )
                candidate = asset_candidate_from_model(artifact)
                if candidate:
                    candidates.append(candidate)
            except Exception as exc:
                logger.warning(
                    "[MessagingHandler] Failed to load artifact %s: %s",
                    artifact_id,
                    exc,
                )

        execution_ids = collect_execution_ids(dispatch_result)
        for execution_id in execution_ids[:12]:
            try:
                artifacts = await asyncio.to_thread(
                    artifacts_store.list_by_execution_id, execution_id
                )
                for artifact in artifacts or []:
                    candidate = asset_candidate_from_model(artifact)
                    if candidate:
                        candidates.append(candidate)
            except Exception as exc:
                logger.warning(
                    "[MessagingHandler] Failed to load execution artifacts %s: %s",
                    execution_id,
                    exc,
                )

        task_ir_id = clean_text(getattr(pipeline_result, "task_ir_id", None))
        if task_ir_id and hasattr(artifacts_store, "list_artifacts_by_task"):
            try:
                artifacts = await asyncio.to_thread(
                    artifacts_store.list_artifacts_by_task, task_ir_id
                )
                for artifact in artifacts or []:
                    candidate = asset_candidate_from_model(artifact)
                    if candidate:
                        candidates.append(candidate)
            except Exception as exc:
                logger.warning(
                    "[MessagingHandler] Failed to load task artifacts %s: %s",
                    task_ir_id,
                    exc,
                )

    assets = await materialize_page_assets(
        dedupe_asset_candidates(candidates),
        workspace_id=workspace_id,
    )
    return format_page_assets_md(assets)
