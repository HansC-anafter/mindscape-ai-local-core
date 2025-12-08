"""
Daily Planning Pack Executor

Executes the daily_planning pack to extract tasks from messages and files.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from backend.app.models.workspace import Task, TaskStatus
from backend.app.models.mindscape import EventType

logger = logging.getLogger(__name__)


class DailyPlanningPackExecutor:
    """Execute Daily Planning Pack to extract tasks"""

    def __init__(self, store, tasks_store, task_manager, llm_provider=None):
        """
        Initialize DailyPlanningPackExecutor

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
        message: str
    ) -> Optional[Task]:
        """
        Execute Daily Planning Pack to extract tasks from messages and files

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            message_id: Message/event ID
            files: List of file IDs
            message: User message (for context)

        Returns:
            Created Task or None if execution failed
        """
        try:
            pack_id = "daily_planning"

            task = Task(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                message_id=message_id,
                execution_id=None,
                pack_id=pack_id,
                task_type="extract_tasks",
                status=TaskStatus.RUNNING,
                params={
                    "files": files,
                    "message": message
                },
                result=None,
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
                completed_at=None,
                error=None
            )
            self.tasks_store.create_task(task)
            logger.info(f"Created daily_planning task: {task.id}")

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

            try:
                self.tasks_store.update_task_status(
                    task_id=task.id,
                    status=TaskStatus.RUNNING,
                    result={
                        "progress": "extracting_tasks",
                        "progress_percentage": 30,
                        "message": "Extracting tasks from content..."
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to update task progress: {e}")

            extracted_tasks = []
            extraction_error = None
            if combined_content:
                try:
                    from .task_extractor import TaskExtractor

                    if self.llm_provider:
                        extractor = TaskExtractor(llm_provider=self.llm_provider)

                        try:
                            self.tasks_store.update_task_status(
                                task_id=task.id,
                                status=TaskStatus.RUNNING,
                                result={
                                    "progress": "extracting_tasks",
                                    "progress_percentage": 50,
                                    "message": "Analyzing content with LLM..."
                                }
                            )
                        except Exception as e:
                            logger.warning(f"Failed to update task progress: {e}")

                        extracted_tasks = await extractor.extract_tasks_from_content(
                            profile_id=profile_id,
                            content=combined_content,
                            source_type="conversation",
                            source_id=message_id,
                            source_context=message
                        )

                        try:
                            self.tasks_store.update_task_status(
                                task_id=task.id,
                                status=TaskStatus.RUNNING,
                                result={
                                    "progress": "processing_results",
                                    "progress_percentage": 80,
                                    "message": f"Extracted {len(extracted_tasks)} tasks, processing results..."
                                }
                            )
                        except Exception as e:
                            logger.warning(f"Failed to update task progress: {e}")
                    else:
                        extraction_error = "LLM provider not available"
                        logger.warning("LLM provider not available, cannot extract tasks")
                except Exception as e:
                    extraction_error = str(e)
                    logger.error(f"Failed to extract tasks using LLM: {e}", exc_info=True)

            if not extracted_tasks:
                error_message = extraction_error or "No actionable tasks found in the content"
                logger.warning(
                    f"daily_planning: No tasks extracted. "
                    f"Content length: {len(combined_content) if combined_content else 0}, "
                    f"Error: {error_message}"
                )
                execution_result = {
                    "title": "Task extraction completed",
                    "summary": f"No actionable tasks found. {error_message}",
                    "message": f"No tasks extracted: {error_message}",
                    "tasks": [],
                    "files_processed": len(files),
                    "extraction_error": error_message
                }
            else:
                execution_result = {
                    "title": f"Extracted {len(extracted_tasks)} tasks",
                    "summary": f"Found {len(extracted_tasks)} actionable tasks from message and files",
                    "message": f"Extracted {len(extracted_tasks)} tasks",
                    "tasks": extracted_tasks[:10],
                    "files_processed": len(files)
                }

            self.tasks_store.update_task_status(
                task_id=task.id,
                status=TaskStatus.SUCCEEDED,
                result={
                    **execution_result,
                    "progress": "completed",
                    "progress_percentage": 100
                },
                completed_at=datetime.utcnow()
            )

            timeline_item = self.task_manager.create_timeline_item_from_task(
                task=task,
                execution_result=execution_result,
                playbook_code=pack_id
            )

            logger.info(f"Completed daily_planning task: {task.id}, created {len(extracted_tasks)} tasks")
            return task

        except Exception as e:
            error_message = f"Failed to execute daily_planning pack: {str(e)}"
            logger.error(error_message, exc_info=True)
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

