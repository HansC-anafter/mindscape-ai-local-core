"""Section builders used by QA and planning context assembly."""

import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ContextSectionsMixin:
    """Build individual context sections from workspace runtime data."""

    async def _build_layered_memory_context(
        self, workspace_id: str, profile_id: Optional[str], project_id: Optional[str]
    ) -> List[str]:
        """Build layered memory context."""
        context_parts = []
        try:
            from backend.app.services.memory.workspace_core_memory import (
                WorkspaceCoreMemoryService,
            )
            from backend.app.services.memory.project_memory import ProjectMemoryService
            from backend.app.services.memory.member_profile_memory import (
                MemberProfileMemoryService,
            )

            workspace_memory_service = WorkspaceCoreMemoryService(self.store)
            workspace_core_memory = await workspace_memory_service.get_core_memory(
                workspace_id
            )
            core_memory_context = workspace_memory_service.format_for_context(
                workspace_core_memory
            )
            if core_memory_context:
                context_parts.append("\n## Workspace Core Memory:")
                context_parts.append(core_memory_context)
                logger.info("Injected workspace core memory into QA context")

            if project_id:
                project_memory_service = ProjectMemoryService(self.store)
                try:
                    project_memory = await project_memory_service.get_project_memory(
                        project_id, workspace_id
                    )
                    project_memory_context = project_memory_service.format_for_context(
                        project_memory
                    )
                    if project_memory_context:
                        context_parts.append("\n## Project Memory:")
                        context_parts.append(project_memory_context)
                        logger.info(f"Injected project memory for project {project_id}")
                except Exception as e:
                    logger.warning(f"Failed to load project memory: {e}")

            if profile_id:
                member_memory_service = MemberProfileMemoryService(self.store)
                try:
                    member_memory = await member_memory_service.get_member_memory(
                        profile_id, workspace_id
                    )
                    member_memory_context = member_memory_service.format_for_context(
                        member_memory, include_experiences=True
                    )
                    if member_memory_context:
                        context_parts.append("\n## Member Profile:")
                        context_parts.append(member_memory_context)
                        logger.info(
                            f"Injected member profile memory for user {profile_id}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to load member memory: {e}")
        except Exception as e:
            logger.warning(f"Failed to load layered memory: {e}")

        return context_parts

    async def _load_governance_context_packet(
        self,
        workspace_id: str,
        profile_id: Optional[str],
        workspace: Optional[Any],
        project_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Load governance-selected memory packet."""
        try:
            from backend.app.services.governance.governance_context_read_model import (
                GovernanceContextReadModel,
            )
            from backend.app.services.mindscape_store import MindscapeStore

            workspace_ref = workspace
            store = self.store or MindscapeStore()
            if workspace_ref is None:
                workspace_ref = await store.get_workspace(workspace_id)

            if workspace_ref is None:
                workspace_ref = SimpleNamespace(
                    id=workspace_id,
                    owner_user_id=profile_id or "",
                    primary_project_id=project_id,
                    mode=None,
                    execution_mode=None,
                    runtime_profile=None,
                    sandbox_config={},
                    metadata={},
                )

            read_model = GovernanceContextReadModel(store=store)
            return await read_model.build_for_workspace(
                workspace_ref,
                profile_id=profile_id,
                project_id=project_id,
            )
        except Exception as e:
            logger.warning(f"Failed to build governance context packet: {e}")
        return None

    def _build_workspace_metadata_context(
        self, workspace: Any, workspace_id: str
    ) -> List[str]:
        """Build workspace metadata context."""
        context_parts = []
        if workspace:
            workspace_info = []
            if workspace.title:
                workspace_info.append(f"Title: {workspace.title}")
            if workspace.description:
                workspace_info.append(f"Description: {workspace.description}")
            if workspace.mode:
                workspace_info.append(f"Mode: {workspace.mode}")
            if workspace_info:
                context_parts.append("\n## Workspace Context:")
                context_parts.extend(workspace_info)
                logger.info(
                    f"Injected workspace metadata: {workspace.title or workspace_id}"
                )
        return context_parts

    async def _build_active_intents_context(
        self, profile_id: Optional[str]
    ) -> List[str]:
        """Build active intents context."""
        context_parts = []
        if profile_id and self.store:
            try:
                from backend.app.models.mindscape import IntentStatus

                active_intents = self.store.list_intents(
                    profile_id=profile_id, status=IntentStatus.ACTIVE
                )
                if active_intents:
                    context_parts.append("\n## Active Intents (Current Goals):")
                    for intent in active_intents[:10]:
                        intent_info = f"- {intent.title}"
                        if intent.description:
                            intent_info += f": {intent.description[:150]}"
                        if intent.priority:
                            intent_info += f" [Priority: {intent.priority.value}]"
                        if intent.progress_percentage is not None:
                            intent_info += (
                                f" [Progress: {intent.progress_percentage:.0f}%]"
                            )
                        context_parts.append(intent_info)
                    logger.info(f"Injected {len(active_intents)} active intents")
            except Exception as e:
                logger.warning(f"Failed to get active intents: {e}")
        return context_parts

    async def _build_current_tasks_context(
        self, workspace_id: str, thread_id: Optional[str]
    ) -> List[str]:
        """Build current tasks context."""
        context_parts = []
        if self.store:
            try:
                from backend.app.services.stores.tasks_store import TasksStore

                tasks_store = TasksStore()

                if thread_id:
                    pending_tasks = tasks_store.list_pending_tasks_by_thread(
                        workspace_id, thread_id
                    )
                    running_tasks = tasks_store.list_running_tasks_by_thread(
                        workspace_id, thread_id
                    )
                else:
                    pending_tasks = tasks_store.list_pending_tasks(workspace_id)
                    running_tasks = tasks_store.list_running_tasks(workspace_id)

                if pending_tasks or running_tasks:
                    context_parts.append("\n## Current Tasks:")

                    tasks_by_intent = {}
                    unlinked_tasks = []

                    for task in (running_tasks + pending_tasks)[:10]:
                        intent_title = None
                        if hasattr(task, "intent_id") and task.intent_id:
                            try:
                                intent = self.store.get_intent(task.intent_id)
                                if intent:
                                    intent_title = intent.title
                            except Exception:
                                pass

                        task_status = (
                            task.status.value
                            if hasattr(task.status, "value")
                            else str(task.status)
                        )
                        task_info = f"- {task.pack_id} ({task_status})"
                        if task.task_type:
                            task_info += f": {task.task_type}"
                        if task.params and isinstance(task.params, dict):
                            source = task.params.get("source", "")
                            if source:
                                task_info += f" [Source: {source}]"

                        if intent_title:
                            if intent_title not in tasks_by_intent:
                                tasks_by_intent[intent_title] = []
                            tasks_by_intent[intent_title].append(task_info)
                        else:
                            unlinked_tasks.append(task_info)

                    for intent_title, task_list in tasks_by_intent.items():
                        context_parts.append(f"\n  Under Intent: {intent_title}")
                        context_parts.extend([f"    {task}" for task in task_list])

                    if unlinked_tasks:
                        context_parts.extend(unlinked_tasks)

                    logger.info(
                        f"Injected {len(pending_tasks) + len(running_tasks)} current tasks"
                    )
            except Exception as e:
                logger.warning(f"Failed to get current tasks: {e}")
        return context_parts

    async def _build_recent_files_context(self, workspace_id: str) -> List[str]:
        """Build recent files context from file analysis events."""
        context_parts = []
        try:
            if self.store:
                recent_events = self.store.get_events_by_workspace(
                    workspace_id=workspace_id, limit=50
                )
                file_events = []
                for event in recent_events:
                    if (
                        hasattr(event, "event_type")
                        and event.event_type.value == "file_analysis"
                    ):
                        payload = (
                            event.payload if isinstance(event.payload, dict) else {}
                        )
                        metadata = (
                            event.metadata if isinstance(event.metadata, dict) else {}
                        )
                        file_analysis = metadata.get("file_analysis", {})
                        if file_analysis:
                            file_events.append(
                                {
                                    "name": payload.get("filename", "Unknown"),
                                    "analysis_summary": file_analysis.get(
                                        "analysis", {}
                                    ).get("summary", ""),
                                    "themes": file_analysis.get("analysis", {}).get(
                                        "themes", []
                                    ),
                                }
                            )

                if file_events:
                    context_parts.append("\n## Recent Files:")
                    for file_ctx in file_events[:3]:
                        file_info = f"- {file_ctx.get('name', 'Unknown')}"
                        if file_ctx.get("analysis_summary"):
                            file_info += f" ({file_ctx.get('analysis_summary')[:100]})"
                        if file_ctx.get("themes"):
                            file_info += f"\n  Themes: {', '.join(file_ctx.get('themes', [])[:5])}"
                        context_parts.append(file_info)
        except Exception as e:
            logger.warning(f"Failed to get file context: {e}")
        return context_parts

    async def _build_timeline_context(
        self, workspace_id: str, thread_id: Optional[str]
    ) -> List[str]:
        """Build timeline context."""
        context_parts = []
        try:
            if self.timeline_items_store:
                if thread_id:
                    recent_timeline_items = (
                        self.timeline_items_store.list_timeline_items_by_thread(
                            workspace_id=workspace_id, thread_id=thread_id, limit=30
                        )
                    )
                else:
                    recent_timeline_items = (
                        self.timeline_items_store.list_timeline_items_by_workspace(
                            workspace_id=workspace_id, limit=30
                        )
                    )
                if recent_timeline_items:
                    context_parts.append("\n## Recent Timeline Activity:")
                    for item in recent_timeline_items[:30]:
                        item_type = (
                            item.type.value
                            if hasattr(item.type, "value")
                            else str(item.type)
                        )
                        item_info = f"- {item_type}: {item.title}"
                        if item.summary:
                            item_info += f" - {item.summary[:200]}"
                        context_parts.append(item_info)
                    logger.info(f"Injected {len(recent_timeline_items)} timeline items")
        except Exception as e:
            logger.error(f"Failed to get timeline context: {e}", exc_info=True)
        return context_parts

    async def _build_thread_references_context(
        self, workspace_id: str, thread_id: Optional[str]
    ) -> List[str]:
        """Build thread references context."""
        context_parts = []
        try:
            if thread_id and self.store:
                thread_references = self.store.thread_references.get_by_thread(
                    workspace_id=workspace_id, thread_id=thread_id, limit=20
                )
                if thread_references:
                    ref_lines = []
                    ref_tokens = 0
                    max_ref_tokens = 500

                    for ref in thread_references:
                        ref_info = f"- [{ref.title}]({ref.uri})"
                        if ref.source_type:
                            ref_info += f" ({ref.source_type})"
                        snippet_text = ""
                        if ref.snippet:
                            snippet_text = f": {ref.snippet[:200]}"
                        if ref.reason:
                            snippet_text += f" [Reason: {ref.reason}]"

                        ref_line = ref_info + snippet_text
                        line_tokens = (
                            self.estimate_token_count(ref_line, self.model_name)
                            or len(ref_line.split()) * 2
                        )

                        if ref_tokens + line_tokens > max_ref_tokens:
                            logger.info(
                                f"Thread references token budget reached ({ref_tokens}/{max_ref_tokens})"
                            )
                            break

                        ref_lines.append(ref_line)
                        ref_tokens += line_tokens

                    if ref_lines:
                        context_parts.append(
                            "\n## Thread References (Pinned Resources):"
                        )
                        context_parts.extend(ref_lines)
                        logger.info(f"Injected {len(ref_lines)} thread references")
        except Exception as e:
            logger.warning(f"Failed to get thread references context: {e}")
        return context_parts
