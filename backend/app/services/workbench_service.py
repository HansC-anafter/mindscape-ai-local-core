"""
Workbench Service

Provides workbench data for workspace including:
- Current context (workspace focus, recent files, detected intents)
- Suggested next steps
- System status (lightweight version)
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.system_health_checker import SystemHealthChecker

logger = logging.getLogger(__name__)


class WorkbenchService:
    """Service for providing workbench data"""

    def __init__(
        self,
        store: Optional[MindscapeStore] = None,
        health_checker: Optional[SystemHealthChecker] = None
    ):
        self.store = store or MindscapeStore()
        self.health_checker = health_checker or SystemHealthChecker()

    async def get_workbench_data(
        self,
        workspace_id: str,
        profile_id: str
    ) -> Dict[str, Any]:
        """
        Get workbench data for a workspace

        Returns:
            Dictionary containing:
            - current_context: Current workspace context
            - suggested_next_steps: Suggested next steps
            - system_status: Lightweight system status
        """
        try:
            workspace = self.store.get_workspace(workspace_id)
            if not workspace:
                raise ValueError(f"Workspace {workspace_id} not found")

            current_context = await self._get_current_context(
                workspace_id=workspace_id,
                profile_id=profile_id
            )

            suggested_next_steps = []
            use_cached = False

            context_fingerprint = self._build_context_fingerprint(current_context)

            if workspace.suggestion_history and len(workspace.suggestion_history) > 0:
                last_round = workspace.suggestion_history[-1]
                cached_fingerprint = last_round.get("context_fingerprint")

                if cached_fingerprint == context_fingerprint:
                    suggested_next_steps = last_round.get("suggestions", [])
                    use_cached = True
                    logger.info(f"Using cached suggestions (context unchanged)")
                else:
                    logger.info(f"Context changed, regenerating suggestions (old: {cached_fingerprint}, new: {context_fingerprint})")
                    use_cached = False

            if not use_cached:
                from backend.app.services.suggestion_generator import SuggestionGenerator
                locale = workspace.default_locale or "zh-TW"
                suggestion_generator = SuggestionGenerator(default_locale=locale)
                suggested_next_steps = await suggestion_generator.generate_suggestions(
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    context=current_context,
                    locale=locale
                )

            if not use_cached:
                if workspace.suggestion_history is None:
                    workspace.suggestion_history = []

                import uuid
                current_round = {
                    "round_id": str(uuid.uuid4()),
                    "timestamp": datetime.utcnow().isoformat(),
                    "suggestions": suggested_next_steps,
                    "context_fingerprint": context_fingerprint
                }
                workspace.suggestion_history.append(current_round)

                if len(workspace.suggestion_history) > 3:
                    workspace.suggestion_history = workspace.suggestion_history[-3:]

                self.store.workspaces.update_workspace(workspace)

            system_status = await self._get_lightweight_system_status(
                profile_id=profile_id
            )

            return {
                "current_context": current_context,
                "suggested_next_steps": suggested_next_steps,
                "suggestion_history": workspace.suggestion_history[-3:] if workspace.suggestion_history else [],  # Include history in response
                "system_status": system_status
            }
        except Exception as e:
            logger.error(f"Failed to get workbench data: {e}", exc_info=True)
            raise

    async def _get_current_context(
        self,
        workspace_id: str,
        profile_id: str
    ) -> Dict[str, Any]:
        """Get current workspace context"""
        try:
            workspace_focus = None
            recent_file = None
            detected_intents = []

            try:
                events = self.store.events.get_events_by_workspace(
                    workspace_id=workspace_id,
                    limit=50
                )

                if events:
                    recent_events = sorted(
                        events,
                        key=lambda e: e.timestamp if hasattr(e, 'timestamp') else datetime.min,
                        reverse=True
                    )[:20]  # Check more events to find the most recent file

                    # Extract assistant messages (LLM outputs) for context
                    assistant_messages = []
                    for event in recent_events[:10]:
                        if hasattr(event, 'event_type'):
                            event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                            if event_type == "message":
                                payload = event.payload if isinstance(event.payload, dict) else {}
                                if isinstance(payload, str):
                                    try:
                                        import json
                                        payload = json.loads(payload)
                                    except:
                                        payload = {}
                                actor = event.actor.value if hasattr(event.actor, 'value') else str(event.actor)
                                if actor == "assistant" and payload.get("message"):
                                    message = payload.get("message", "")
                                    if message and len(message) > 50:  # Only substantial messages
                                        assistant_messages.append({
                                            "message": message[:500],  # Limit length
                                            "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp)
                                        })

                    # Store assistant messages in context for playbook matching
                    context_assistant_messages = assistant_messages[:3]  # Keep top 3 most recent

                    # Track all file uploads to find the most recent one
                    file_candidates = []

                    for event in recent_events:
                        if hasattr(event, 'event_type'):
                            event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                            if event_type == "message":
                                payload = event.payload if isinstance(event.payload, dict) else {}
                                if isinstance(payload, str):
                                    try:
                                        import json
                                        payload = json.loads(payload)
                                    except:
                                        payload = {}

                                actor = event.actor.value if hasattr(event.actor, 'value') else str(event.actor)
                                if actor == "user" and payload.get("files"):
                                    files = payload.get("files", [])
                                    if files and len(files) > 0:
                                        # Process each file in the event
                                        for file_item in files:
                                            file_info = file_item if isinstance(file_item, dict) else {}

                                            # Try to get file name from analysis metadata if available
                                            metadata = event.metadata if isinstance(event.metadata, dict) else {}

                                            analysis_file_info = None
                                            if metadata.get("file_analysis"):
                                                file_analysis = metadata["file_analysis"]
                                                if isinstance(file_analysis, dict) and file_analysis.get("file_info"):
                                                    analysis_file_info = file_analysis["file_info"]

                                            # Prefer file name from analysis, then payload, then message
                                            file_name = None
                                            if analysis_file_info and isinstance(analysis_file_info, dict):
                                                file_name = analysis_file_info.get("name")
                                            if not file_name and isinstance(file_info, dict):
                                                file_name = file_info.get("name")
                                            if not file_name:
                                                # Try to extract from message
                                                message = payload.get("message", "")
                                                if "已上傳檔案:" in message or "已上傳檔案：" in message:
                                                    import re
                                                    match = re.search(r'已上傳檔案[:：]\s*(.+)', message)
                                                    if match:
                                                        file_name = match.group(1).strip()

                                            if not file_name:
                                                file_name = "Unknown file"

                                            # Add to candidates with timestamp
                                            event_timestamp = event.timestamp if hasattr(event, 'timestamp') else datetime.utcnow()
                                            file_candidates.append({
                                                "name": file_name,
                                                "uploaded_at": event_timestamp.isoformat(),
                                                "timestamp": event_timestamp
                                            })

                    # Get the most recent file (by timestamp)
                    if file_candidates:
                        most_recent = max(file_candidates, key=lambda f: f["timestamp"])
                        recent_file = {
                            "name": most_recent["name"],
                            "uploaded_at": most_recent["uploaded_at"]
                        }
                        logger.info(f"Selected most recent file from {len(file_candidates)} candidates: {recent_file}")

                    workspace_focus = self._extract_workspace_focus(recent_events)
            except Exception as e:
                logger.warning(f"Failed to get events for context: {e}")

            detected_intents = self._get_detected_intents(profile_id, workspace_id)

            # Get recent timeline items (LLM outputs) for playbook matching
            recent_timeline_items = []
            try:
                from backend.app.services.stores.timeline_items_store import TimelineItemsStore
                timeline_store = TimelineItemsStore(self.store.db_path)
                timeline_items = timeline_store.list_timeline_items_by_workspace(
                    workspace_id=workspace_id,
                    limit=10
                )
                # Filter for content-rich items (include all types, but prioritize actual content outputs)
                # LLM outputs might be stored as various types (PLAN, DRAFT, SUMMARY, etc.)
                recent_timeline_items = [
                    {
                        "id": item.id,
                        "type": item.type.value if hasattr(item.type, 'value') else str(item.type),
                        "title": item.title or "",
                        "summary": item.summary or "",
                        "data": item.data or {},
                        "created_at": item.created_at.isoformat() if hasattr(item.created_at, 'isoformat') else str(item.created_at)
                    }
                    for item in timeline_items
                    # Include all types except INTENT_SEEDS (which are just suggestions, not actual outputs)
                    # LLM outputs are typically PLAN, DRAFT, SUMMARY, or custom types
                    if item.type.value not in ['INTENT_SEEDS']
                ][:10]  # Get top 10 most recent content items for better analysis
                logger.info(f"Found {len(recent_timeline_items)} recent timeline items for playbook matching")
            except Exception as e:
                logger.warning(f"Failed to get timeline items for context: {e}")

            return {
                "workspace_focus": workspace_focus or None,
                "workspace_focus_key": None if workspace_focus else "noClearWorkspaceFocus",
                "recent_file": recent_file,
                "detected_intents": detected_intents,
                "recent_timeline_items": recent_timeline_items,  # Add timeline items for playbook matching
                "recent_assistant_messages": context_assistant_messages if 'context_assistant_messages' in locals() else []  # Add assistant messages (LLM outputs)
            }
        except Exception as e:
            logger.error(f"Failed to get current context: {e}", exc_info=True)
            return {
                "workspace_focus": None,
                "workspace_focus_key": "failedToGetWorkspaceFocus",
                "recent_file": None,
                "detected_intents": []
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
            # First, try to get from recent timeline items (LLM outputs)
            try:
                from backend.app.services.stores.timeline_items_store import TimelineItemsStore
                timeline_store = TimelineItemsStore(self.store.db_path)
                # Get workspace_id from events if available
                workspace_id = None
                for event in events[:5]:
                    if hasattr(event, 'workspace_id') and event.workspace_id:
                        workspace_id = event.workspace_id
                        break

                if workspace_id:
                    timeline_items = timeline_store.list_timeline_items_by_workspace(
                        workspace_id=workspace_id,
                        limit=5
                    )
                    # Look for content-rich items (exclude INTENT_SEEDS)
                    for item in timeline_items:
                        if item.type.value not in ['INTENT_SEEDS']:
                            # Prefer items with titles that indicate task-level content
                            if item.title and len(item.title) > 10:
                                # Check if title suggests structured content
                                title_lower = item.title.lower()
                                if any(kw in title_lower for kw in ["課程", "規劃", "表格", "時間表", "course", "plan", "table", "schedule"]):
                                    return item.title[:100]  # Use title as focus
                            # Fallback to summary if title not available
                            if item.summary and len(item.summary) > 20:
                                return item.summary[:100]
            except Exception as e:
                logger.debug(f"Could not get workspace focus from timeline items: {e}")

            # Second, try to get from recent file uploads with analysis
            for event in events[:10]:
                if hasattr(event, 'event_type'):
                    event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                    if event_type == "message":
                        payload = event.payload if isinstance(event.payload, dict) else {}
                        if isinstance(payload, str):
                            try:
                                import json
                                payload = json.loads(payload)
                            except:
                                payload = {}

                        # Check for file upload with analysis
                        if payload.get("files"):
                            metadata = event.metadata if isinstance(event.metadata, dict) else {}
                            if metadata.get("file_analysis"):
                                file_analysis = metadata["file_analysis"]
                                file_info = file_analysis.get("file_info", {})
                                file_name = file_info.get("name", "")
                                if file_name:
                                    # Extract meaningful name (remove extension, clean up)
                                    import os
                                    name_without_ext = os.path.splitext(file_name)[0]
                                    # Limit length
                                    if len(name_without_ext) > 50:
                                        name_without_ext = name_without_ext[:47] + "..."
                                    return name_without_ext

                        # Skip welcome messages (they contain i18n keys, not actual content)
                        if payload.get("is_welcome"):
                            continue

                        # Check for user message about specific task
                        message = payload.get("message", "")
                        if message and len(message) > 5 and len(message) < 100:
                            # Skip i18n keys (they contain dots and are not actual messages)
                            if "." in message and message.startswith(("welcome.", "suggestions.")):
                                continue
                            # Simple heuristic: if message looks like a task description
                            if any(keyword in message for keyword in ["草稿", "企劃", "報告", "專案", "任務", "draft", "proposal", "report", "project"]):
                                return message[:80]  # Limit length

            # Fallback: try to get from recent events
            for event in events[:5]:
                if hasattr(event, 'event_type'):
                    event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                    if event_type == "message":
                        payload = event.payload if isinstance(event.payload, dict) else {}
                        if isinstance(payload, str):
                            try:
                                import json
                                payload = json.loads(payload)
                            except:
                                payload = {}
                        # Skip welcome messages
                        if payload.get("is_welcome"):
                            continue
                        message = payload.get("message", "")
                        if message and len(message) > 10:
                            # Skip i18n keys
                            if "." in message and message.startswith(("welcome.", "suggestions.")):
                                continue
                            return message[:100] + "..." if len(message) > 100 else message
            return None
        except Exception as e:
            logger.warning(f"Failed to extract workspace focus: {e}")
            return None

    def _get_detected_intents(
        self,
        profile_id: str,
        workspace_id: str
    ) -> List[Dict[str, Any]]:
        """Get detected intents for the workspace"""
        try:
            intents = self.store.list_intents(
                profile_id=profile_id,
                status=None,
                priority=None
            )

            # Filter by workspace_id if available in metadata
            workspace_intents = []
            for intent in intents:
                # Check if intent belongs to this workspace
                intent_workspace_id = None
                if intent.metadata and isinstance(intent.metadata, dict):
                    intent_workspace_id = intent.metadata.get('workspace_id')

                # Include intent if it matches workspace or has no workspace_id (legacy)
                if intent_workspace_id == workspace_id or intent_workspace_id is None:
                    workspace_intents.append(intent)

            # Limit to 5 most recent
            workspace_intents = sorted(
                workspace_intents,
                key=lambda x: x.created_at if hasattr(x, 'created_at') else datetime.min,
                reverse=True
            )[:5]

            detected = []
            for intent in workspace_intents:
                detected.append({
                    "id": intent.id,
                    "title": intent.title,
                    "source": "mindscape",
                    "status": intent.status.value if hasattr(intent.status, 'value') else str(intent.status)
                })

            logger.info(f"Found {len(detected)} intents for workspace {workspace_id}")
            return detected
        except Exception as e:
            logger.warning(f"Failed to get detected intents: {e}")
            return []

    async def _get_suggested_next_steps(
        self,
        workspace_id: str,
        profile_id: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get suggested next steps based on context and recent messages"""
        try:
            suggestions = []

            # Get recent user messages to understand what they're working on
            recent_user_messages = []
            try:
                events = self.store.events.get_events_by_workspace(
                    workspace_id=workspace_id,
                    limit=20
                )
                for event in events[:10]:
                    if hasattr(event, 'event_type'):
                        event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                        if event_type == "message":
                            payload = event.payload if isinstance(event.payload, dict) else {}
                            if isinstance(payload, str):
                                try:
                                    import json
                                    payload = json.loads(payload)
                                except:
                                    payload = {}
                            actor = event.actor.value if hasattr(event.actor, 'value') else str(event.actor)
                            if actor == "user" and payload.get("message"):
                                message = payload.get("message", "")
                                if message and len(message) > 3:
                                    recent_user_messages.append(message.lower())
            except Exception as e:
                logger.warning(f"Failed to get recent messages: {e}")

            # Generate suggestions based on recent messages
            if recent_user_messages:
                latest_message = recent_user_messages[0] if recent_user_messages else ""

                # Task organization related
                if any(keyword in latest_message for keyword in ["整理", "任務", "待辦", "todo", "task", "organize", "整理今天", "今天任務"]):
                    suggestions.append({
                        "type": "task_organization",
                        "title_key": "organizeTasks",
                        "description_key": "createTaskChecklist",
                        "action": "organize_tasks",
                        "priority": "high"
                    })

                # Planning related
                elif any(keyword in latest_message for keyword in ["規劃", "計劃", "plan", "schedule", "安排"]):
                    suggestions.append({
                        "type": "planning",
                        "title_key": "createPlan",
                        "description_key": "breakDownIntoSteps",
                        "action": "create_plan",
                        "priority": "high"
                    })

                # Writing related
                elif any(keyword in latest_message for keyword in ["寫", "起草", "文案", "文章", "write", "draft", "content"]):
                    suggestions.append({
                        "type": "writing",
                        "title_key": "draftContent",
                        "description_key": "createDraft",
                        "action": "draft_content",
                        "priority": "high"
                    })

                # Research related - REMOVED: Generic keyword-based suggestions are too vague
                # Only suggest research if there's actual context (files, timeline items, etc.)
                # This prevents generic "研究主題" suggestions without context
                # elif any(keyword in latest_message for keyword in ["研究", "分析", "資料", "research", "analyze", "資料"]):
                #     suggestions.append({
                #         "type": "research",
                #         "title_key": "researchTopic",
                #         "description_key": "gatherInformation",
                #         "action": "research",
                #         "priority": "high"
                #     })

            # File-related suggestions
            if context.get("recent_file"):
                suggestions.append({
                    "type": "file_analysis",
                    "title_key": "analyzeUploadedFile",
                    "description_key": "uploadedFileWithName",
                    "description_params": {"file_name": context['recent_file']['name']},
                    "action": "analyze_file",
                    "priority": "high"
                })

            # Intent-related suggestions
            if not context.get("detected_intents") or len(context.get("detected_intents", [])) == 0:
                suggestions.append({
                    "type": "create_intent",
                    "title_key": "createFirstIntentCard",
                    "description_key": "startTrackingLongTermGoals",
                    "action": "create_intent",
                    "priority": "medium"
                })

            # Default suggestion if nothing specific
            if len(suggestions) == 0:
                suggestions.append({
                    "type": "start_chat",
                    "title_key": "startChat",
                    "description_key": "tellMeWhatYouWantToComplete",
                    "action": "start_chat",
                    "priority": "low"
                })

            # Limit to 3 most relevant suggestions
            return suggestions[:3]
        except Exception as e:
            logger.warning(f"Failed to get suggested next steps: {e}")
            return []

    def _build_context_fingerprint(
        self,
        context: Dict[str, Any]
    ) -> str:
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
                "recent_file": context.get("recent_file", {}).get("name") if context.get("recent_file") else None,
                "timeline_items_count": len(context.get("recent_timeline_items", [])),
                "timeline_item_ids": [item.get("id") for item in context.get("recent_timeline_items", [])[:5]],
                "intents_count": len(context.get("detected_intents", [])),
                "assistant_messages_count": len(context.get("recent_assistant_messages", []))
            }

            fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
            fingerprint_hash = hashlib.md5(fingerprint_str.encode()).hexdigest()

            return fingerprint_hash
        except Exception as e:
            logger.warning(f"Failed to build context fingerprint: {e}")
            return ""

    async def _get_lightweight_system_status(
        self,
        profile_id: str
    ) -> Dict[str, Any]:
        """Get lightweight system status (without full issue details)"""
        try:
            full_health = await self.health_checker.check_workspace_health(
                profile_id=profile_id
            )

            critical_issues = [
                issue for issue in full_health.get("issues", [])
                if issue.get("severity") == "error"
            ]

            return {
                "llm_configured": full_health.get("llm_configured", False),
                "llm_provider": full_health.get("llm_provider"),
                "vector_db_connected": full_health.get("vector_db_connected", False),
                "tools": full_health.get("tools", {}),
                "critical_issues_count": len(critical_issues),
                "has_issues": len(critical_issues) > 0
            }
        except Exception as e:
            logger.error(f"Failed to get lightweight system status: {e}", exc_info=True)
            return {
                "llm_configured": False,
                "llm_provider": None,
                "vector_db_connected": False,
                "tools": {},
                "critical_issues_count": 1,
                "has_issues": True
            }
