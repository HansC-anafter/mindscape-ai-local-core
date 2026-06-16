"""
Workbench detected-intent, legacy suggestion, and fingerprint helpers.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger("backend.app.services.workbench_service")


class WorkbenchSuggestionsMixin:
    """Mixin: intents, legacy suggestions, and context fingerprinting."""

    def _get_detected_intents(
        self, profile_id: str, workspace_id: str
    ) -> List[Dict[str, Any]]:
        """Get detected intents for the workspace"""
        try:
            intents = self.store.list_intents(
                profile_id=profile_id, status=None, priority=None
            )

            workspace_intents = []
            for intent in intents:
                intent_workspace_id = None
                if intent.metadata and isinstance(intent.metadata, dict):
                    intent_workspace_id = intent.metadata.get("workspace_id")

                if intent_workspace_id == workspace_id or intent_workspace_id is None:
                    workspace_intents.append(intent)

            workspace_intents = sorted(
                workspace_intents,
                key=lambda x: (
                    x.created_at if hasattr(x, "created_at") else datetime.min
                ),
                reverse=True,
            )[:5]

            detected = []
            for intent in workspace_intents:
                detected.append(
                    {
                        "id": intent.id,
                        "title": intent.title,
                        "source": "mindscape",
                        "status": (
                            intent.status.value
                            if hasattr(intent.status, "value")
                            else str(intent.status)
                        ),
                    }
                )

            logger.info(f"Found {len(detected)} intents for workspace {workspace_id}")
            return detected
        except Exception as e:
            logger.warning(f"Failed to get detected intents: {e}")
            return []

    async def _get_suggested_next_steps(
        self, workspace_id: str, profile_id: str, context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get suggested next steps based on context and recent messages"""
        try:
            suggestions = []

            recent_user_messages = []
            try:
                events = self.store.events.get_events_by_workspace(
                    workspace_id=workspace_id, limit=20
                )
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
                            actor = (
                                event.actor.value
                                if hasattr(event.actor, "value")
                                else str(event.actor)
                            )
                            if actor == "user" and payload.get("message"):
                                message = payload.get("message", "")
                                if message and len(message) > 3:
                                    recent_user_messages.append(message.lower())
            except Exception as e:
                logger.warning(f"Failed to get recent messages: {e}")

            if recent_user_messages:
                latest_message = recent_user_messages[0] if recent_user_messages else ""

                if any(
                    keyword in latest_message
                    for keyword in [
                        "整理",
                        "任務",
                        "待辦",
                        "todo",
                        "task",
                        "organize",
                        "整理今天",
                        "今天任務",
                    ]
                ):
                    suggestions.append(
                        {
                            "type": "task_organization",
                            "title_key": "organizeTasks",
                            "description_key": "createTaskChecklist",
                            "action": "organize_tasks",
                            "priority": "high",
                        }
                    )

                elif any(
                    keyword in latest_message
                    for keyword in ["規劃", "計劃", "plan", "schedule", "安排"]
                ):
                    suggestions.append(
                        {
                            "type": "planning",
                            "title_key": "createPlan",
                            "description_key": "breakDownIntoSteps",
                            "action": "create_plan",
                            "priority": "high",
                        }
                    )

                elif any(
                    keyword in latest_message
                    for keyword in [
                        "寫",
                        "起草",
                        "文案",
                        "文章",
                        "write",
                        "draft",
                        "content",
                    ]
                ):
                    suggestions.append(
                        {
                            "type": "writing",
                            "title_key": "draftContent",
                            "description_key": "createDraft",
                            "action": "draft_content",
                            "priority": "high",
                        }
                    )

            if context.get("recent_file"):
                suggestions.append(
                    {
                        "type": "file_analysis",
                        "title_key": "analyzeUploadedFile",
                        "description_key": "uploadedFileWithName",
                        "description_params": {
                            "file_name": context["recent_file"]["name"]
                        },
                        "action": "analyze_file",
                        "priority": "high",
                    }
                )

            if (
                not context.get("detected_intents")
                or len(context.get("detected_intents", [])) == 0
            ):
                suggestions.append(
                    {
                        "type": "create_intent",
                        "title_key": "createFirstIntentCard",
                        "description_key": "startTrackingLongTermGoals",
                        "action": "create_intent",
                        "priority": "medium",
                    }
                )

            if len(suggestions) == 0:
                suggestions.append(
                    {
                        "type": "start_chat",
                        "title_key": "startChat",
                        "description_key": "tellMeWhatYouWantToComplete",
                        "action": "start_chat",
                        "priority": "low",
                    }
                )

            return suggestions[:3]
        except Exception as e:
            logger.warning(f"Failed to get suggested next steps: {e}")
            return []

    def _build_context_fingerprint(self, context: Dict[str, Any]) -> str:
        """
        Build a fingerprint of the current context to detect changes.
        This fingerprint is used to determine if suggestions should be regenerated.

        The fingerprint includes:
        - Workspace focus (what user is working on)
        - Recent file (if any)
        - Recent timeline items (count and IDs of most recent)
        - Detected intents (count)
        - Recent assistant messages (count)

        This ensures suggestions are only regenerated when context actually changes,
        not on every API call.
        """
        try:
            import hashlib
            import json

            fingerprint_data = {
                "workspace_focus": context.get("workspace_focus") or "",
                "recent_file": (
                    context.get("recent_file", {}).get("name")
                    if context.get("recent_file")
                    else None
                ),
                "timeline_items_count": len(context.get("recent_timeline_items", [])),
                "timeline_item_ids": [
                    item.get("id")
                    for item in context.get("recent_timeline_items", [])[:5]
                ],
                "intents_count": len(context.get("detected_intents", [])),
                "assistant_messages_count": len(
                    context.get("recent_assistant_messages", [])
                ),
            }

            fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
            fingerprint_hash = hashlib.md5(fingerprint_str.encode()).hexdigest()

            return fingerprint_hash
        except Exception as e:
            logger.warning(f"Failed to build context fingerprint: {e}")
            return ""
