"""
Workbench current-context and workspace-focus helpers.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("backend.app.services.workbench_service")


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class WorkbenchContextMixin:
    """Mixin: workbench context and focus extraction."""

    async def _get_current_context(
        self, workspace_id: str, profile_id: str
    ) -> Dict[str, Any]:
        """Get current workspace context"""
        try:
            workspace_focus = None
            recent_file = None
            detected_intents = []

            try:
                events = self.store.events.get_events_by_workspace(
                    workspace_id=workspace_id, limit=50
                )

                if events:
                    recent_events = sorted(
                        events,
                        key=lambda e: (
                            e.timestamp if hasattr(e, "timestamp") else datetime.min
                        ),
                        reverse=True,
                    )[:20]

                    assistant_messages = []
                    for event in recent_events[:10]:
                        if hasattr(event, "event_type"):
                            event_type = (
                                event.event_type.value
                                if hasattr(event.event_type, "value")
                                else str(event.event_type)
                            )
                            if event_type == "message":
                                payload = (
                                    event.payload
                                    if isinstance(event.payload, dict)
                                    else {}
                                )
                                if isinstance(payload, str):
                                    try:
                                        import json

                                        payload = json.loads(payload)
                                    except:
                                        payload = {}
                                actor = (
                                    event.actor.value
                                    if hasattr(event.actor, "value")
                                    else str(event.actor)
                                )
                                if actor == "assistant" and payload.get("message"):
                                    message = payload.get("message", "")
                                    if message and len(message) > 50:
                                        assistant_messages.append(
                                            {
                                                "message": message[:500],
                                                "timestamp": (
                                                    event.timestamp.isoformat()
                                                    if hasattr(
                                                        event.timestamp, "isoformat"
                                                    )
                                                    else str(event.timestamp)
                                                ),
                                            }
                                        )

                    context_assistant_messages = assistant_messages[:3]
                    file_candidates = []

                    for event in recent_events:
                        if hasattr(event, "event_type"):
                            event_type = (
                                event.event_type.value
                                if hasattr(event.event_type, "value")
                                else str(event.event_type)
                            )
                            if event_type == "message":
                                payload = (
                                    event.payload
                                    if isinstance(event.payload, dict)
                                    else {}
                                )
                                if isinstance(payload, str):
                                    try:
                                        import json

                                        payload = json.loads(payload)
                                    except:
                                        payload = {}

                                actor = (
                                    event.actor.value
                                    if hasattr(event.actor, "value")
                                    else str(event.actor)
                                )
                                if actor == "user" and payload.get("files"):
                                    files = payload.get("files", [])
                                    if files and len(files) > 0:
                                        for file_item in files:
                                            file_info = (
                                                file_item
                                                if isinstance(file_item, dict)
                                                else {}
                                            )

                                            metadata = (
                                                event.metadata
                                                if isinstance(event.metadata, dict)
                                                else {}
                                            )

                                            analysis_file_info = None
                                            if metadata.get("file_analysis"):
                                                file_analysis = metadata[
                                                    "file_analysis"
                                                ]
                                                if isinstance(
                                                    file_analysis, dict
                                                ) and file_analysis.get("file_info"):
                                                    analysis_file_info = file_analysis[
                                                        "file_info"
                                                    ]

                                            file_name = None
                                            if analysis_file_info and isinstance(
                                                analysis_file_info, dict
                                            ):
                                                file_name = analysis_file_info.get(
                                                    "name"
                                                )
                                            if not file_name and isinstance(
                                                file_info, dict
                                            ):
                                                file_name = file_info.get("name")
                                            if not file_name:
                                                message = payload.get("message", "")
                                                if (
                                                    "已上傳檔案:" in message
                                                    or "已上傳檔案：" in message
                                                ):
                                                    import re

                                                    match = re.search(
                                                        r"已上傳檔案[:：]\s*(.+)",
                                                        message,
                                                    )
                                                    if match:
                                                        file_name = match.group(
                                                            1
                                                        ).strip()

                                            if not file_name:
                                                file_name = "Unknown file"

                                            event_timestamp = (
                                                event.timestamp
                                                if hasattr(event, "timestamp")
                                                else _utc_now()
                                            )
                                            file_candidates.append(
                                                {
                                                    "name": file_name,
                                                    "uploaded_at": event_timestamp.isoformat(),
                                                    "timestamp": event_timestamp,
                                                }
                                            )

                    if file_candidates:
                        most_recent = max(file_candidates, key=lambda f: f["timestamp"])
                        recent_file = {
                            "name": most_recent["name"],
                            "uploaded_at": most_recent["uploaded_at"],
                        }
                        logger.info(
                            f"Selected most recent file from {len(file_candidates)} candidates: {recent_file}"
                        )

                    workspace_focus = self._extract_workspace_focus(recent_events)
            except Exception as e:
                logger.warning(f"Failed to get events for context: {e}")

            detected_intents = self._get_detected_intents(profile_id, workspace_id)

            recent_timeline_items = []
            try:
                from backend.app.services.stores.postgres.timeline_items_store import (
                    PostgresTimelineItemsStore,
                )

                timeline_store = PostgresTimelineItemsStore()
                timeline_items = timeline_store.list_timeline_items_by_workspace(
                    workspace_id=workspace_id, limit=10
                )
                recent_timeline_items = [
                    {
                        "id": item.id,
                        "type": (
                            item.type.value
                            if hasattr(item.type, "value")
                            else str(item.type)
                        ),
                        "title": item.title or "",
                        "summary": item.summary or "",
                        "data": item.data or {},
                        "created_at": (
                            item.created_at.isoformat()
                            if hasattr(item.created_at, "isoformat")
                            else str(item.created_at)
                        ),
                    }
                    for item in timeline_items
                    if item.type.value not in ["INTENT_SEEDS"]
                ][:10]
                logger.info(
                    f"Found {len(recent_timeline_items)} recent timeline items for playbook matching"
                )
            except Exception as e:
                logger.warning(f"Failed to get timeline items for context: {e}")

            return {
                "workspace_focus": workspace_focus or None,
                "workspace_focus_key": (
                    None if workspace_focus else "noClearWorkspaceFocus"
                ),
                "recent_file": recent_file,
                "detected_intents": detected_intents,
                "recent_timeline_items": recent_timeline_items,
                "recent_assistant_messages": (
                    context_assistant_messages
                    if "context_assistant_messages" in locals()
                    else []
                ),
            }
        except Exception as e:
            logger.error(f"Failed to get current context: {e}", exc_info=True)
            return {
                "workspace_focus": None,
                "workspace_focus_key": "failedToGetWorkspaceFocus",
                "recent_file": None,
                "detected_intents": [],
            }

    def _extract_workspace_focus(self, events: List) -> Optional[str]:
        """Extract workspace focus from recent events

        Priority:
        1. Recent timeline items with rich content (LLM outputs)
        2. Recent file upload with analysis (use file name)
        3. Recent user message about a specific task
        4. Recent intent title
        """
        try:
            try:
                from backend.app.services.stores.postgres.timeline_items_store import (
                    PostgresTimelineItemsStore,
                )

                timeline_store = PostgresTimelineItemsStore()
                workspace_id = None
                for event in events[:5]:
                    if hasattr(event, "workspace_id") and event.workspace_id:
                        workspace_id = event.workspace_id
                        break

                if workspace_id:
                    timeline_items = timeline_store.list_timeline_items_by_workspace(
                        workspace_id=workspace_id, limit=5
                    )
                    for item in timeline_items:
                        if item.type.value not in ["INTENT_SEEDS"]:
                            if item.title and len(item.title) > 10:
                                title_lower = item.title.lower()
                                if any(
                                    kw in title_lower
                                    for kw in [
                                        "課程",
                                        "規劃",
                                        "表格",
                                        "時間表",
                                        "course",
                                        "plan",
                                        "table",
                                        "schedule",
                                    ]
                                ):
                                    return item.title[:100]
                            if item.summary and len(item.summary) > 20:
                                return item.summary[:100]
            except Exception as e:
                logger.debug(f"Could not get workspace focus from timeline items: {e}")

            for event in events[:10]:
                if hasattr(event, "event_type"):
                    event_type = (
                        event.event_type.value
                        if hasattr(event.event_type, "value")
                        else str(event.event_type)
                    )
                    if event_type == "message":
                        payload = (
                            event.payload if isinstance(event.payload, dict) else {}
                        )
                        if isinstance(payload, str):
                            try:
                                import json

                                payload = json.loads(payload)
                            except:
                                payload = {}

                        if payload.get("files"):
                            metadata = (
                                event.metadata
                                if isinstance(event.metadata, dict)
                                else {}
                            )
                            if metadata.get("file_analysis"):
                                file_analysis = metadata["file_analysis"]
                                file_info = file_analysis.get("file_info", {})
                                file_name = file_info.get("name", "")
                                if file_name:
                                    import os

                                    name_without_ext = os.path.splitext(file_name)[0]
                                    if len(name_without_ext) > 50:
                                        name_without_ext = name_without_ext[:47] + "..."
                                    return name_without_ext

                        if payload.get("is_welcome"):
                            continue

                        message = payload.get("message", "")
                        if message and len(message) > 5 and len(message) < 100:
                            if "." in message and message.startswith(
                                ("welcome.", "suggestions.")
                            ):
                                continue
                            if any(
                                keyword in message
                                for keyword in [
                                    "草稿",
                                    "企劃",
                                    "報告",
                                    "專案",
                                    "任務",
                                    "draft",
                                    "proposal",
                                    "report",
                                    "project",
                                ]
                            ):
                                return message[:80]

            for event in events[:5]:
                if hasattr(event, "event_type"):
                    event_type = (
                        event.event_type.value
                        if hasattr(event.event_type, "value")
                        else str(event.event_type)
                    )
                    if event_type == "message":
                        payload = (
                            event.payload if isinstance(event.payload, dict) else {}
                        )
                        if isinstance(payload, str):
                            try:
                                import json

                                payload = json.loads(payload)
                            except:
                                payload = {}
                        if payload.get("is_welcome"):
                            continue
                        message = payload.get("message", "")
                        if message and len(message) > 10:
                            if "." in message and message.startswith(
                                ("welcome.", "suggestions.")
                            ):
                                continue
                            return (
                                message[:100] + "..." if len(message) > 100 else message
                            )
            return None
        except Exception as e:
            logger.warning(f"Failed to extract workspace focus: {e}")
            return None
