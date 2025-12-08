"""
Content Drafting Pack Executor

Executes the content_drafting pack to generate summaries and drafts.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from backend.app.models.workspace import Task, TaskStatus
from backend.app.models.mindscape import EventType

logger = logging.getLogger(__name__)


class ContentDraftingPackExecutor:
    """Execute Content Drafting Pack to generate summaries and drafts"""

    def __init__(self, store, tasks_store, task_manager, llm_provider=None):
        """
        Initialize ContentDraftingPackExecutor

        Args:
            store: MindscapeStore instance
            tasks_store: TasksStore instance
            task_manager: TaskManager instance
            llm_provider: LLM provider instance (optional)
        """
        self.store = store
        self.tasks_store = tasks_store
        self.task_manager = task_manager
        self.llm_provider = llm_provider

    async def execute(
        self,
        workspace_id: str,
        profile_id: str,
        message_id: str,
        files: List[str],
        message: str,
        output_type: str = "summary"
    ) -> Optional[Task]:
        """
        Execute Content Drafting Pack to generate summary or draft

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            message_id: Message/event ID
            files: List of file IDs
            message: User message (for context)
            output_type: 'summary' or 'draft'

        Returns:
            Created Task or None if execution failed
        """
        try:
            pack_id = "content_drafting"

            task = Task(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                message_id=message_id,
                execution_id=None,
                pack_id=pack_id,
                task_type=f"generate_{output_type}",
                status=TaskStatus.RUNNING,
                params={
                    "files": files,
                    "message": message,
                    "output_type": output_type
                },
                result=None,
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
                completed_at=None,
                error=None
            )
            self.tasks_store.create_task(task)
            logger.info(f"Created content_drafting task: {task.id}, type: {output_type}")

            content_parts = []

            if message:
                content_parts.append(f"Message: {message}")

            recent_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=50
            )

            file_contents = []
            for event in recent_events:
                if event.event_type == EventType.MESSAGE:
                    payload = event.payload if isinstance(event.payload, dict) else {}
                    metadata = event.metadata if isinstance(event.metadata, dict) else {}

                    file_analysis = metadata.get('file_analysis', {})
                    analysis = file_analysis.get('analysis', {})
                    file_info = analysis.get('file_info', {})

                    if file_info.get('text_content'):
                        file_contents.append(file_info['text_content'])

            if file_contents:
                content_parts.append(f"\n\nFile Content:\n{chr(10).join(file_contents[:3])}")

            combined_content = "\n".join(content_parts)

            generated_content = {}
            if combined_content:
                try:
                    from .content_generator import ContentGenerator

                    if self.llm_provider:
                        generator = ContentGenerator(llm_provider=self.llm_provider)

                        if output_type == "summary":
                            generated_content = await generator.generate_summary(
                                profile_id=profile_id,
                                content=combined_content,
                                source_type="conversation",
                                source_id=message_id,
                                source_context=message
                            )
                        else:
                            format_type = "blog_post"
                            if "article" in message.lower():
                                format_type = "article"
                            elif "report" in message.lower():
                                format_type = "report"

                            generated_content = await generator.generate_draft(
                                profile_id=profile_id,
                                content=combined_content,
                                format=format_type,
                                source_type="conversation",
                                source_id=message_id,
                                source_context=message
                            )
                    else:
                        logger.warning("LLM provider not available, cannot generate content")
                except Exception as e:
                    logger.warning(f"Failed to generate content using LLM: {e}")

            if output_type == "summary":
                execution_result = {
                    "title": "Generated Summary",
                    "summary": generated_content.get("summary", ""),
                    "key_points": generated_content.get("key_points", []),
                    "themes": generated_content.get("themes", []),
                    "message": "Summary generated successfully",
                    "files_processed": len(files)
                }
            else:
                execution_result = {
                    "title": generated_content.get("title", "Generated Draft"),
                    "summary": f"Draft generated in {generated_content.get('format', 'blog_post')} format",
                    "content": generated_content.get("content", ""),
                    "tags": generated_content.get("tags", []),
                    "format": generated_content.get("format", "blog_post"),
                    "message": "Draft generated successfully",
                    "files_processed": len(files)
                }

            self.tasks_store.update_task_status(
                task_id=task.id,
                status=TaskStatus.SUCCEEDED,
                result=execution_result,
                completed_at=datetime.utcnow()
            )

            timeline_item = self.task_manager.create_timeline_item_from_task(
                task=task,
                execution_result=execution_result,
                playbook_code=pack_id
            )

            logger.info(f"Completed content_drafting task: {task.id}, type: {output_type}")
            return task

        except Exception as e:
            logger.error(f"Failed to execute content_drafting pack: {e}", exc_info=True)
            if 'task' in locals():
                try:
                    self.tasks_store.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=str(e),
                        completed_at=datetime.utcnow()
                    )
                except Exception:
                    pass
            return None

