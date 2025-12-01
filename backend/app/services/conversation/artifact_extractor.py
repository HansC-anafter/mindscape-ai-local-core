"""
Artifact Extractor Service

Extracts artifacts from playbook execution results and creates Artifact records.
Supports multiple playbook types with different output formats.
"""

import logging
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from ...models.workspace import Artifact, ArtifactType, PrimaryActionType, Task
from ...services.mindscape_store import MindscapeStore
from ...services.storage_path_resolver import StoragePathResolver

logger = logging.getLogger(__name__)


class ArtifactExtractor:
    """Extract artifacts from playbook execution results"""

    def __init__(self, store: MindscapeStore):
        """
        Initialize ArtifactExtractor

        Args:
            store: MindscapeStore instance for accessing workspace configuration
        """
        self.store = store

    def extract_artifact_from_task_result(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        playbook_code: str,
        intent_id: Optional[str] = None
    ) -> Optional[Artifact]:
        """
        Extract artifact from task execution result

        Args:
            task: Completed task
            execution_result: Execution result data
            playbook_code: Playbook code
            intent_id: Optional intent ID (extracted from execution_result or task)

        Returns:
            Artifact model or None if no artifact can be extracted
        """
        try:
            # Extract intent_id if not provided
            if not intent_id:
                intent_id = self._extract_intent_id(task, execution_result)

            # Route to specific extractor based on playbook_code
            playbook_lower = playbook_code.lower()

            if "daily_planning" in playbook_lower or "planning" in playbook_lower:
                return self._extract_daily_planning_artifact(task, execution_result, intent_id)
            elif "content_drafting" in playbook_lower or "draft" in playbook_lower:
                return self._extract_content_drafting_artifact(task, execution_result, intent_id)
            elif "major_proposal" in playbook_lower or "proposal" in playbook_lower:
                return self._extract_major_proposal_artifact(task, execution_result, intent_id)
            elif "campaign_asset" in playbook_lower or "canva" in playbook_lower:
                return self._extract_campaign_asset_artifact(task, execution_result, intent_id)
            elif "audio" in playbook_lower or "recording" in playbook_lower or "voice" in playbook_lower:
                return self._extract_audio_artifact(task, execution_result, intent_id)
            else:
                # Try generic extraction for unknown playbooks
                logger.debug(f"No specific extractor for playbook {playbook_code}, trying generic extraction")
                return self._extract_generic_artifact(task, execution_result, playbook_code, intent_id)

        except Exception as e:
            logger.error(f"Failed to extract artifact from task {task.id}: {e}", exc_info=True)
            return None

    def _extract_intent_id(
        self,
        task: Task,
        execution_result: Dict[str, Any]
    ) -> Optional[str]:
        """
        Extract intent_id from task or execution_result

        Priority:
        1. execution_result.intent_id
        2. task.intent_id (if exists)
        3. task.metadata.intent_id (if exists)

        Args:
            task: Task object
            execution_result: Execution result dict

        Returns:
            Intent ID or None
        """
        # Check execution_result first
        if isinstance(execution_result, dict):
            intent_id = execution_result.get("intent_id")
            if intent_id:
                return intent_id

        # Check task.intent_id (if Task model has this field)
        if hasattr(task, 'intent_id') and task.intent_id:
            return task.intent_id

        # Check task.metadata
        if hasattr(task, 'metadata') and isinstance(task.metadata, dict):
            intent_id = task.metadata.get("intent_id")
            if intent_id:
                return intent_id

        return None

    def _extract_daily_planning_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """
        Extract checklist artifact from daily_planning playbook

        Expected execution_result structure:
        {
            "title": str,
            "summary": str,
            "message": str,
            "tasks": List[dict],  # List of task objects
            "files_processed": int
        }

        Args:
            task: Task object
            execution_result: Execution result dict
            intent_id: Optional intent ID

        Returns:
            Artifact or None
        """
        tasks = execution_result.get("tasks", [])
        extraction_error = execution_result.get("extraction_error")

        # Format tasks as checklist
        checklist_items = []

        if not tasks:
            error_message = extraction_error or "No actionable tasks found in the content"
            logger.warning(
                f"daily_planning: No tasks found in execution_result. "
                f"execution_result keys: {list(execution_result.keys())}, "
                f"tasks value: {execution_result.get('tasks')}, "
                f"title: {execution_result.get('title')}, "
                f"summary: {execution_result.get('summary')}, "
                f"message: {execution_result.get('message')}, "
                f"extraction_error: {extraction_error}"
            )

            # Create an artifact with error information instead of returning None
            # This allows users to see why no tasks were extracted
            # Create empty checklist with error note
            checklist_items = [{
                "id": str(uuid.uuid4()),
                "title": f"⚠️ {error_message}",
                "description": "No actionable tasks were found in the content. Please check the input or try again with more specific content.",
                "priority": "",
                "completed": False
            }]
        else:
            # Format tasks as checklist
            for idx, task_item in enumerate(tasks[:10], 1):  # Limit to 10 tasks
                if isinstance(task_item, dict):
                    title = task_item.get("title") or task_item.get("task") or f"Task {idx}"
                    description = task_item.get("description") or task_item.get("details") or ""
                    priority = task_item.get("priority") or task_item.get("urgency") or ""
                    checklist_items.append({
                        "id": task_item.get("id") or str(uuid.uuid4()),
                        "title": title,
                        "description": description,
                        "priority": priority,
                        "completed": False
                    })
                elif isinstance(task_item, str):
                    checklist_items.append({
                        "id": str(uuid.uuid4()),
                        "title": task_item,
                        "description": "",
                        "priority": "",
                        "completed": False
                    })

        if not checklist_items:
            logger.warning(
                f"daily_planning: No checklist items created from tasks. "
                f"tasks: {tasks}, tasks type: {type(tasks)}, tasks length: {len(tasks) if isinstance(tasks, list) else 'N/A'}"
            )
            return None

        # Set title and summary based on whether tasks were found
        if not tasks:
            # Use error-aware title and summary when no tasks found
            error_message = extraction_error or "No actionable tasks found in the content"
            title = execution_result.get("title") or "Task extraction completed"
            summary = execution_result.get("summary") or f"No tasks extracted: {error_message}"
        else:
            # Normal title and summary when tasks were found
            title = execution_result.get("title") or f"Daily Planning - {len(checklist_items)} tasks"
            summary = execution_result.get("summary") or f"Extracted {len(checklist_items)} tasks"

        # Attempt to write to workspace-bound path
        storage_ref = None
        write_failed = False
        write_error = None

        try:
            # Get storage path
            storage_path = self._get_artifact_storage_path(
                workspace_id=task.workspace_id,
                playbook_code="daily_planning",
                intent_id=intent_id,
                artifact_type=ArtifactType.CHECKLIST.value
            )

            # Generate filename
            filename = self._generate_artifact_filename(
                workspace_id=task.workspace_id,
                playbook_code="daily_planning",
                artifact_type=ArtifactType.CHECKLIST.value,
                title=title
            )

            target_path = storage_path / filename

            # Check for conflicts
            conflict_info = self._check_file_conflict(
                target_path=target_path,
                workspace_id=task.workspace_id,
                playbook_code="daily_planning",
                artifact_type=ArtifactType.CHECKLIST.value
            )

            if conflict_info.get("has_conflict"):
                # If conflict exists, regenerate filename with suggested version
                suggested_version = conflict_info.get("suggested_version")
                if suggested_version:
                    filename = self._generate_artifact_filename(
                        workspace_id=task.workspace_id,
                        playbook_code="daily_planning",
                        artifact_type=ArtifactType.CHECKLIST.value,
                        title=title,
                        version=suggested_version
                    )
                    target_path = storage_path / filename

            # Prepare content (JSON format)
            import json
            content_bytes = json.dumps({
                "tasks": checklist_items,
                "total_count": len(checklist_items),
                "files_processed": execution_result.get("files_processed", 0),
                "title": title,
                "summary": summary
            }, indent=2, ensure_ascii=False).encode('utf-8')

            # Atomic write
            self._write_artifact_file_atomic(content_bytes, target_path)

            storage_ref = str(target_path)
            logger.info(f"Successfully wrote checklist artifact to {storage_ref}")

        except Exception as e:
            write_failed = True
            write_error = str(e)
            logger.warning(f"Failed to write checklist artifact to workspace path: {e}. Artifact will be created without file storage.")
            # If file write fails, still create artifact but record error

        metadata = {
            "extracted_at": datetime.utcnow().isoformat(),
            "source": "daily_planning"
        }
        if write_failed:
            metadata["write_failed"] = True
            metadata["write_error"] = write_error

        return Artifact(
            id=str(uuid.uuid4()),
            workspace_id=task.workspace_id,
            intent_id=intent_id,
            task_id=task.id,
            execution_id=task.execution_id,
            playbook_code="daily_planning",
            artifact_type=ArtifactType.CHECKLIST,
            title=title,
            summary=summary,
            content={
                "tasks": checklist_items,
                "total_count": len(checklist_items),
                "files_processed": execution_result.get("files_processed", 0)
            },
            storage_ref=storage_ref,
            sync_state=None,
            primary_action_type=PrimaryActionType.COPY,
            metadata=metadata,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def _extract_content_drafting_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """
        Extract draft artifact from content_drafting playbook

        Expected execution_result structure for draft:
        {
            "title": str,
            "summary": str,
            "content": str,  # Markdown content
            "tags": List[str],
            "format": str,  # "blog_post", "article", "report"
            "message": str,
            "files_processed": int
        }

        Expected execution_result structure for summary:
        {
            "title": str,
            "summary": str,
            "key_points": List[str],
            "themes": List[str],
            "message": str,
            "files_processed": int
        }

        Args:
            task: Task object
            execution_result: Execution result dict
            intent_id: Optional intent ID

        Returns:
            Artifact or None
        """
        # Check if this is a draft or summary
        content = execution_result.get("content")
        if content:
            # This is a draft
            title = execution_result.get("title") or "Generated Draft"
            summary = execution_result.get("summary") or f"Draft in {execution_result.get('format', 'blog_post')} format"

            # Attempt to write to workspace-bound path
            storage_ref = None
            write_failed = False
            write_error = None

            try:
                # Get storage path
                storage_path = self._get_artifact_storage_path(
                    workspace_id=task.workspace_id,
                    playbook_code="content_drafting",
                    intent_id=intent_id,
                    artifact_type=ArtifactType.DRAFT.value
                )

                # Generate filename
                filename = self._generate_artifact_filename(
                    workspace_id=task.workspace_id,
                    playbook_code="content_drafting",
                    artifact_type=ArtifactType.DRAFT.value,
                    title=title
                )

                target_path = storage_path / filename

                # Check for conflicts
                conflict_info = self._check_file_conflict(
                    target_path=target_path,
                    workspace_id=task.workspace_id,
                    playbook_code="content_drafting",
                    artifact_type=ArtifactType.DRAFT.value
                )

                if conflict_info.get("has_conflict"):
                    # If conflict exists, regenerate filename with suggested version
                    suggested_version = conflict_info.get("suggested_version")
                    if suggested_version:
                        filename = self._generate_artifact_filename(
                            workspace_id=task.workspace_id,
                            playbook_code="content_drafting",
                            artifact_type=ArtifactType.DRAFT.value,
                            title=title,
                            version=suggested_version
                        )
                        target_path = storage_path / filename

                # Prepare content (Markdown)
                content_bytes = content.encode('utf-8')

                # Atomic write
                self._write_artifact_file_atomic(content_bytes, target_path)

                storage_ref = str(target_path)
                logger.info(f"Successfully wrote draft artifact to {storage_ref}")

            except Exception as e:
                write_failed = True
                write_error = str(e)
                logger.warning(f"Failed to write draft artifact to workspace path: {e}. Artifact will be created without file storage.")

            metadata = {
                "extracted_at": datetime.utcnow().isoformat(),
                "source": "content_drafting",
                "output_type": "draft"
            }
            if write_failed:
                metadata["write_failed"] = True
                metadata["write_error"] = write_error

            return Artifact(
                id=str(uuid.uuid4()),
                workspace_id=task.workspace_id,
                intent_id=intent_id,
                task_id=task.id,
                execution_id=task.execution_id,
                playbook_code="content_drafting",
                artifact_type=ArtifactType.DRAFT,
                title=title,
                summary=summary,
                content={
                    "content": content,
                    "format": execution_result.get("format", "blog_post"),
                    "tags": execution_result.get("tags", []),
                    "files_processed": execution_result.get("files_processed", 0)
                },
                storage_ref=storage_ref,
                sync_state=None,
                primary_action_type=PrimaryActionType.COPY,
                metadata=metadata,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        else:
            # This is a summary - also create artifact but as draft type
            # Try to extract meaningful title and summary from content
            raw_summary = execution_result.get("summary") or ""
            raw_content = execution_result.get("content") or ""

            # Extract title from various sources
            title = (
                execution_result.get("title") or
                execution_result.get("document_title") or
                (raw_summary.split('\n')[0][:100] if raw_summary else None) or
                (raw_content.split('\n')[0][:100] if raw_content else None) or
                "內容摘要"
            )

            # Extract meaningful summary
            if raw_summary and raw_summary.strip() and raw_summary.strip() != "Summary generated":
                summary = raw_summary[:200] if len(raw_summary) > 200 else raw_summary
            elif raw_content:
                # Extract first meaningful paragraph from content
                content_lines = [line.strip() for line in raw_content.split('\n') if line.strip()]
                if content_lines:
                    summary = content_lines[0][:200] if len(content_lines[0]) > 200 else content_lines[0]
                else:
                    summary = "已生成內容摘要"
            else:
                summary = "已生成內容摘要"

            # Format summary content
            summary_content = raw_summary or raw_content or summary
            if execution_result.get("key_points"):
                summary_content += "\n\nKey Points:\n" + "\n".join(f"- {point}" for point in execution_result.get("key_points", []))
            if execution_result.get("themes"):
                summary_content += "\n\nThemes:\n" + "\n".join(f"- {theme}" for theme in execution_result.get("themes", []))

            return Artifact(
                id=str(uuid.uuid4()),
                workspace_id=task.workspace_id,
                intent_id=intent_id,
                task_id=task.id,
                execution_id=task.execution_id,
                playbook_code="content_drafting",
                artifact_type=ArtifactType.DRAFT,
                title=title,
                summary=summary,
                content={
                    "content": summary_content,
                    "key_points": execution_result.get("key_points", []),
                    "themes": execution_result.get("themes", []),
                    "files_processed": execution_result.get("files_processed", 0)
                },
                storage_ref=None,
                sync_state=None,
                primary_action_type=PrimaryActionType.COPY,
                metadata={
                    "extracted_at": datetime.utcnow().isoformat(),
                    "source": "content_drafting",
                    "output_type": "summary"
                },
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

    def _extract_major_proposal_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """
        Extract DOCX artifact from major_proposal playbook and write to workspace storage

        Expected execution_result structure:
        {
            "file_path": str,  # Path to generated DOCX file (may be temporary)
            "title": str,
            "summary": str,
            ...
        }

        Args:
            task: Task object
            execution_result: Execution result dict
            intent_id: Optional intent ID

        Returns:
            Artifact or None
        """
        source_file_path = execution_result.get("file_path") or execution_result.get("docx_path")
        if not source_file_path:
            logger.debug("major_proposal: No file_path found in execution_result")
            return None

        title = execution_result.get("title") or "Proposal Document"
        summary = execution_result.get("summary") or "Generated proposal document"

        # Get storage path (workspace-bound path)
        try:
            storage_dir = self._get_artifact_storage_path(
                workspace_id=task.workspace_id,
                playbook_code="major_proposal_writing",
                intent_id=intent_id,
                artifact_type=ArtifactType.DOCX.value
            )
        except (ValueError, PermissionError) as e:
            logger.error(f"Failed to get storage path for major_proposal artifact: {e}")
            # If storage path unavailable, use original path (backward compatibility)
            storage_ref = source_file_path
            logger.warning(f"Using original file path as storage_ref: {storage_ref}")
        else:
            # Generate filename with version number
            filename = self._generate_artifact_filename(
                workspace_id=task.workspace_id,
                playbook_code="major_proposal_writing",
                artifact_type=ArtifactType.DOCX.value,
                title=title
            )
            target_path = storage_dir / filename

            # Check for conflicts
            conflict_info = self._check_file_conflict(
                target_path=target_path,
                workspace_id=task.workspace_id,
                playbook_code="major_proposal_writing",
                artifact_type=ArtifactType.DOCX.value,
                force=False
            )

            if conflict_info.get("has_conflict") and conflict_info.get("suggested_version"):
                suggested_version = conflict_info.get("suggested_version")
                # Regenerate filename with suggested version
                filename = self._generate_artifact_filename(
                    workspace_id=task.workspace_id,
                    playbook_code="major_proposal_writing",
                    artifact_type=ArtifactType.DOCX.value,
                    title=title,
                    version=suggested_version
                )
                target_path = storage_dir / filename

            # Use file lock and atomic write
            try:
                with self._file_lock(storage_dir):
                    # Read source file content
                    source_path = Path(source_file_path)
                    if not source_path.exists():
                        logger.warning(f"Source file not found: {source_file_path}, using original path")
                        storage_ref = source_file_path
                    else:
                        with open(source_path, 'rb') as f:
                            file_content = f.read()

                        # Atomic write to target path
                        self._write_artifact_file_atomic(file_content, target_path)
                        storage_ref = str(target_path)
                        logger.info(f"Successfully wrote DOCX artifact to {storage_ref}")
            except Exception as e:
                logger.error(f"Failed to write artifact file: {e}, using original path")
                storage_ref = source_file_path

        return Artifact(
            id=str(uuid.uuid4()),
            workspace_id=task.workspace_id,
            intent_id=intent_id,
            task_id=task.id,
            execution_id=task.execution_id,
            playbook_code="major_proposal_writing",
            artifact_type=ArtifactType.DOCX,
            title=title,
            summary=summary,
            content={
                "file_path": storage_ref,
                "file_name": Path(storage_ref).name,
                "original_path": source_file_path
            },
            storage_ref=storage_ref,
            sync_state=None,
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "extracted_at": datetime.utcnow().isoformat(),
                "source": "major_proposal_writing"
            },
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def _extract_campaign_asset_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """
        Extract Canva artifact from campaign_asset_playbook

        Expected execution_result structure:
        {
            "canva_url": str,  # Canva design URL
            "thumbnail_url": str,  # Optional thumbnail
            "title": str,
            "summary": str,
            ...
        }

        Args:
            task: Task object
            execution_result: Execution result dict
            intent_id: Optional intent ID

        Returns:
            Artifact or None
        """
        canva_url = execution_result.get("canva_url") or execution_result.get("url") or execution_result.get("design_url")
        if not canva_url:
            logger.debug("campaign_asset: No canva_url found in execution_result")
            return None

        title = execution_result.get("title") or "Campaign Asset"
        summary = execution_result.get("summary") or "Canva design created"

        return Artifact(
            id=str(uuid.uuid4()),
            workspace_id=task.workspace_id,
            intent_id=intent_id,
            task_id=task.id,
            execution_id=task.execution_id,
            playbook_code="campaign_asset_playbook",
            artifact_type=ArtifactType.CANVA,
            title=title,
            summary=summary,
            content={
                "canva_url": canva_url,
                "thumbnail_url": execution_result.get("thumbnail_url"),
                "design_id": execution_result.get("design_id")
            },
            storage_ref=canva_url,
            sync_state=None,
            primary_action_type=PrimaryActionType.OPEN_EXTERNAL,
            metadata={
                "extracted_at": datetime.utcnow().isoformat(),
                "source": "campaign_asset_playbook"
            },
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def _extract_audio_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """
        Extract audio artifact from audio recording playbook and write to workspace storage

        Expected execution_result structure:
        {
            "audio_file_path": str,  # Path to audio file (may be temporary)
            "transcript": str,  # Optional transcript
            "title": str,
            "summary": str,
            ...
        }

        Args:
            task: Task object
            execution_result: Execution result dict
            intent_id: Optional intent ID

        Returns:
            Artifact or None
        """
        source_audio_path = execution_result.get("audio_file_path") or execution_result.get("file_path") or execution_result.get("audio_path")
        if not source_audio_path:
            logger.debug("audio: No audio_file_path found in execution_result")
            return None

        title = execution_result.get("title") or "Audio Recording"
        summary = execution_result.get("summary") or "Audio recording completed"

        # Get storage path (workspace-bound path)
        try:
            storage_dir = self._get_artifact_storage_path(
                workspace_id=task.workspace_id,
                playbook_code="ai_guided_recording",
                intent_id=intent_id,
                artifact_type=ArtifactType.AUDIO.value
            )
        except (ValueError, PermissionError) as e:
            logger.error(f"Failed to get storage path for audio artifact: {e}")
            # If storage path unavailable, use original path (backward compatibility)
            storage_ref = source_audio_path
            logger.warning(f"Using original file path as storage_ref: {storage_ref}")
        else:
            # Generate filename with version number
            filename = self._generate_artifact_filename(
                workspace_id=task.workspace_id,
                playbook_code="ai_guided_recording",
                artifact_type=ArtifactType.AUDIO.value,
                title=title
            )
            target_path = storage_dir / filename

            # Check for conflicts
            conflict_info = self._check_file_conflict(
                target_path=target_path,
                workspace_id=task.workspace_id,
                playbook_code="ai_guided_recording",
                artifact_type=ArtifactType.AUDIO.value,
                force=False
            )

            if conflict_info.get("has_conflict") and conflict_info.get("suggested_version"):
                suggested_version = conflict_info.get("suggested_version")
                # Regenerate filename with suggested version
                filename = self._generate_artifact_filename(
                    workspace_id=task.workspace_id,
                    playbook_code="ai_guided_recording",
                    artifact_type=ArtifactType.AUDIO.value,
                    title=title,
                    version=suggested_version
                )
                target_path = storage_dir / filename

            # Use file lock and atomic write
            try:
                with self._file_lock(storage_dir):
                    # Read source file content
                    source_path = Path(source_audio_path)
                    if not source_path.exists():
                        logger.warning(f"Source file not found: {source_audio_path}, using original path")
                        storage_ref = source_audio_path
                    else:
                        with open(source_path, 'rb') as f:
                            file_content = f.read()

                        # Atomic write to target path
                        self._write_artifact_file_atomic(file_content, target_path)
                        storage_ref = str(target_path)
                        logger.info(f"Successfully wrote audio artifact to {storage_ref}")
            except Exception as e:
                logger.error(f"Failed to write artifact file: {e}, using original path")
                storage_ref = source_audio_path

        return Artifact(
            id=str(uuid.uuid4()),
            workspace_id=task.workspace_id,
            intent_id=intent_id,
            task_id=task.id,
            execution_id=task.execution_id,
            playbook_code="ai_guided_recording",
            artifact_type=ArtifactType.AUDIO,
            title=title,
            summary=summary,
            content={
                "audio_file_path": storage_ref,
                "transcript": execution_result.get("transcript"),
                "duration": execution_result.get("duration"),
                "file_size": execution_result.get("file_size"),
                "original_path": source_audio_path
            },
            storage_ref=storage_ref,
            sync_state=None,
            primary_action_type=PrimaryActionType.DOWNLOAD,
            metadata={
                "extracted_at": datetime.utcnow().isoformat(),
                "source": "ai_guided_recording"
            },
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def _extract_generic_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        playbook_code: str,
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """
        Generic artifact extraction for unknown playbooks

        Tries to extract any meaningful content from execution_result.

        Args:
            task: Task object
            execution_result: Execution result dict
            playbook_code: Playbook code
            intent_id: Optional intent ID

        Returns:
            Artifact or None
        """
        # Check if there's any extractable content
        title = execution_result.get("title")
        summary = execution_result.get("summary") or execution_result.get("message")
        content = execution_result.get("content") or execution_result.get("result")

        if not (title or summary or content):
            logger.debug(f"generic: No extractable content found for playbook {playbook_code}")
            return None

        # Determine artifact type based on content
        artifact_type = ArtifactType.DRAFT
        primary_action = PrimaryActionType.COPY

        # Check for specific content types
        if execution_result.get("file_path") or execution_result.get("docx_path"):
            artifact_type = ArtifactType.DOCX
            primary_action = PrimaryActionType.DOWNLOAD
        elif execution_result.get("canva_url") or execution_result.get("url"):
            artifact_type = ArtifactType.CANVA
            primary_action = PrimaryActionType.OPEN_EXTERNAL
        elif execution_result.get("tasks") or execution_result.get("checklist"):
            artifact_type = ArtifactType.CHECKLIST
            primary_action = PrimaryActionType.COPY

        # Attempt to write to workspace-bound path (if no existing file_path)
        storage_ref = execution_result.get("file_path") or execution_result.get("storage_ref")
        write_failed = False
        write_error = None

        if not storage_ref:
            # Only attempt write if no existing storage_ref
            try:
                # Get storage path
                storage_path = self._get_artifact_storage_path(
                    workspace_id=task.workspace_id,
                    playbook_code=playbook_code,
                    intent_id=intent_id,
                    artifact_type=artifact_type.value
                )

                # Generate filename
                filename = self._generate_artifact_filename(
                    workspace_id=task.workspace_id,
                    playbook_code=playbook_code,
                    artifact_type=artifact_type.value,
                    title=title or playbook_code
                )

                target_path = storage_path / filename

                # Check for conflicts
                conflict_info = self._check_file_conflict(
                    target_path=target_path,
                    workspace_id=task.workspace_id,
                    playbook_code=playbook_code,
                    artifact_type=artifact_type.value
                )

                if conflict_info.get("has_conflict"):
                    # If conflict exists, regenerate filename with suggested version
                    suggested_version = conflict_info.get("suggested_version")
                    if suggested_version:
                        filename = self._generate_artifact_filename(
                            workspace_id=task.workspace_id,
                            playbook_code=playbook_code,
                            artifact_type=artifact_type.value,
                            title=title or playbook_code,
                            version=suggested_version
                        )
                        target_path = storage_path / filename

                # Prepare content (format based on type)
                if artifact_type == ArtifactType.CHECKLIST:
                    import json
                    content_bytes = json.dumps(execution_result, indent=2, ensure_ascii=False).encode('utf-8')
                elif artifact_type == ArtifactType.DRAFT:
                    # Markdown format
                    content_str = content if isinstance(content, str) else str(content)
                    content_bytes = content_str.encode('utf-8')
                else:
                    # JSON format
                    import json
                    content_bytes = json.dumps(execution_result, indent=2, ensure_ascii=False).encode('utf-8')

                # Atomic write
                self._write_artifact_file_atomic(content_bytes, target_path)

                storage_ref = str(target_path)
                logger.info(f"Successfully wrote generic artifact to {storage_ref}")

            except Exception as e:
                write_failed = True
                write_error = str(e)
                logger.warning(f"Failed to write generic artifact to workspace path: {e}. Artifact will be created without file storage.")

        metadata = {
            "extracted_at": datetime.utcnow().isoformat(),
            "source": "generic_extraction",
            "playbook_code": playbook_code
        }
        if write_failed:
            metadata["write_failed"] = True
            metadata["write_error"] = write_error

        return Artifact(
            id=str(uuid.uuid4()),
            workspace_id=task.workspace_id,
            intent_id=intent_id,
            task_id=task.id,
            execution_id=task.execution_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type,
            title=title or playbook_code,
            summary=summary or f"Output from {playbook_code}",
            content=execution_result,
            storage_ref=storage_ref,
            sync_state=None,
            primary_action_type=primary_action,
            metadata=metadata,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def _get_artifact_storage_path(
        self,
        workspace_id: str,
        playbook_code: str,
        intent_id: Optional[str] = None,
        artifact_type: str = "file",
        execution_storage_config: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Get artifact storage path with priority resolution (execution → playbook → workspace → default)

        Path structure:
        <base_path>/<artifacts_dir>/<playbook_code>/[<intent_id>/][<date>/]

        Security requirement: Must validate path is within allowed directories

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            intent_id: Optional intent ID (for bucketing)
            artifact_type: Artifact type (for extension)
            execution_storage_config: Optional execution-specific storage config

        Returns:
            Path object pointing to storage directory
        """
        # Get Workspace
        workspace = self.store.workspaces.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace not found: {workspace_id}")

        # Use StoragePathResolver to get path with priority
        storage_path = StoragePathResolver.get_artifact_storage_path(
            workspace=workspace,
            playbook_code=playbook_code,
            intent_id=intent_id,
            artifact_type=artifact_type,
            execution_storage_config=execution_storage_config
        )

        # Security check: validate path is within allowed directories (prevent directory traversal)
        # Critical security check, must execute after all path construction
        allowed_dirs = self._get_allowed_directories()
        if allowed_dirs:
            if not self._validate_path_in_allowed_directories(storage_path, allowed_dirs):
                raise ValueError(
                    f"Storage path {storage_path} is not within allowed directories. "
                    "This may indicate a security issue or misconfiguration."
                )
        else:
            # Log warning when no allowed directories configured (but still allow execution)
            logger.warning(
                f"No allowed directories configured for workspace {workspace_id}. "
                "Path validation skipped. This may be a security risk."
            )

        return storage_path

    def _get_allowed_directories(self) -> List[str]:
        """獲取允許目錄列表（重用 workspace.py 中的函數）"""
        from ...routes.workspace import _get_allowed_directories
        return _get_allowed_directories()

    def _validate_path_in_allowed_directories(
        self,
        path: Path,
        allowed_directories: List[str]
    ) -> bool:
        """驗證路徑是否在允許目錄內（重用 workspace.py 中的函數）"""
        from ...routes.workspace import _validate_path_in_allowed_directories
        return _validate_path_in_allowed_directories(path, allowed_directories)

    def _sanitize_filename(self, filename: str, max_length: int = 200) -> str:
        """
        清理檔名，移除非法字元、保留字，確保跨平台兼容性

        Args:
            filename: 原始檔名
            max_length: 最大長度（預設 200）

        Returns:
            清理後的檔名
        """
        import re
        import platform

        # Remove or replace illegal characters (Windows: < > : " | ? * \ /)
        # Linux/macOS: / and null byte
        illegal_chars = r'[<>:"|?*\x00/]'
        sanitized = re.sub(illegal_chars, '-', filename)

        # Windows reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
        reserved_names = [
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        ]

        # Check if reserved name (case-insensitive)
        base_name = sanitized.split('.')[0].upper()
        if base_name in reserved_names:
            sanitized = f"file-{sanitized}"

        # Remove leading and trailing dots and spaces (Windows disallows)
        sanitized = sanitized.strip('. ')

        # Limit length
        if len(sanitized) > max_length:
            # Preserve extension
            if '.' in sanitized:
                name, ext = sanitized.rsplit('.', 1)
                max_name_length = max_length - len(ext) - 1
                sanitized = name[:max_name_length] + '.' + ext
            else:
                sanitized = sanitized[:max_length]

        # Ensure not empty
        if not sanitized or sanitized == '.':
            sanitized = 'file'

        return sanitized

    def _generate_artifact_filename(
        self,
        workspace_id: str,
        playbook_code: str,
        artifact_type: str,
        title: str,
        version: Optional[int] = None,
        extension: Optional[str] = None
    ) -> str:
        """
        生成產物檔名

        格式：<slug>-v<序號>-<timestamp>.<ext>

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook 代碼
            artifact_type: 產物類型
            title: 產物標題（用於生成 slug）
            version: 版本號（如果為 None，則從 DB 查詢最新版本）
            extension: 副檔名（如果為 None，則根據 artifact_type 推斷）

        Returns:
            檔名字符串（已清理非法字元）
        """
        # Generate slug from title
        import re
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug[:50]
        if not slug:
            # If slug empty, use playbook_code
            slug = playbook_code.lower()[:50]

        # Get version number
        if version is None:
            version = self._get_next_version(workspace_id, playbook_code, artifact_type)

        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Get extension
        if extension is None:
            extension = self._get_extension_for_artifact_type(artifact_type)

        # Combine filename
        filename = f"{slug}-v{version}-{timestamp}.{extension}"

        # Sanitize filename (remove illegal chars, reserved names, limit length)
        filename = self._sanitize_filename(filename, max_length=200)

        return filename

    def _get_next_version(
        self,
        workspace_id: str,
        playbook_code: str,
        artifact_type: str
    ) -> int:
        """
        Get next version number

        Query DB for latest version of same playbook and artifact_type, return next version number.

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            artifact_type: Artifact type

        Returns:
            Next version number (starting from 1)
        """
        # Query DB for latest version of same playbook and artifact_type
        artifacts = self.store.artifacts.list_artifacts_by_playbook(
            workspace_id, playbook_code
        )

        # Filter same artifact_type
        same_type_artifacts = [
            a for a in artifacts
            if a.artifact_type.value == artifact_type or str(a.artifact_type) == artifact_type
        ]

        if not same_type_artifacts:
            return 1

        # Get maximum version number (read from metadata)
        max_version = 1
        for artifact in same_type_artifacts:
            version = artifact.metadata.get("version", 1) if artifact.metadata else 1
            if isinstance(version, int) and version > max_version:
                max_version = version

        return max_version + 1

    def _get_extension_for_artifact_type(self, artifact_type: str) -> str:
        """
        Get file extension based on artifact_type

        Args:
            artifact_type: Artifact type (string or ArtifactType enum value)

        Returns:
            File extension string (without dot)
        """
        # Handle ArtifactType enum
        if isinstance(artifact_type, ArtifactType):
            artifact_type = artifact_type.value

        extension_map = {
            "docx": "docx",
            "draft": "md",
            "checklist": "md",
            "config": "json",
            "audio": "mp3",
            "canva": "url",
        }
        return extension_map.get(artifact_type, "txt")

    def _write_artifact_file_atomic(
        self,
        content: bytes,
        target_path: Path
    ) -> None:
        """
        Atomically write file

        Uses temp file + fsync + rename to ensure atomicity, avoiding file corruption during write.

        Args:
            content: Content to write (bytes)
            target_path: Target file path

        Raises:
            OSError: If write fails
        """
        import tempfile
        import os

        # Create temp file (in same directory)
        temp_file = tempfile.NamedTemporaryFile(
            mode='wb',
            dir=target_path.parent,
            delete=False,
            suffix='.tmp'
        )

        try:
            # Write content
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_file.close()

            # Atomically move to target path
            os.rename(temp_file.name, str(target_path))
            logger.debug(f"Atomically wrote file: {target_path}")

        except Exception as e:
            # Cleanup temp file
            if os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file {temp_file.name}: {cleanup_error}")
            raise

    @staticmethod
    def _file_lock(lock_path: Path, timeout: int = 10):
        """
        File lock context manager

        Uses portalocker to implement cross-platform file locking (at directory level), preventing concurrent write conflicts.

        Args:
            lock_path: Directory where lock file is located
            timeout: Timeout for acquiring lock (seconds)

        Yields:
            None (used as context manager)

        Raises:
            ImportError: If portalocker is not installed
            TimeoutError: If lock acquisition times out

        Usage:
            with ArtifactExtractor._file_lock(storage_path):
                # Execute file write operation
                pass
        """
        # Try to import portalocker
        try:
            import portalocker
        except ImportError:
            raise ImportError(
                "portalocker is required for cross-platform file locking. "
                "Install it with: pip install portalocker>=2.0.0"
            )

        import time
        from contextlib import contextmanager

        @contextmanager
        def _lock_context():
            lock_file = lock_path / ".artifact.lock"
            lock_file.parent.mkdir(parents=True, exist_ok=True)

            lock_fd = None
            try:
                # Open lock file
                lock_fd = open(lock_file, 'w')

                # Try to acquire lock (non-blocking)
                start_time = time.time()
                while True:
                    try:
                        portalocker.lock(lock_fd, portalocker.LOCK_EX | portalocker.LOCK_NB)
                        break
                    except (BlockingIOError, OSError):
                        # Lock is held, wait
                        if time.time() - start_time > timeout:
                            raise TimeoutError(
                                f"Failed to acquire lock on {lock_path} after {timeout}s"
                            )
                        time.sleep(0.1)

                yield

            finally:
                # Release lock
                if lock_fd:
                    try:
                        portalocker.unlock(lock_fd)
                    except Exception as unlock_error:
                        logger.warning(f"Failed to unlock file: {unlock_error}")
                    try:
                        lock_fd.close()
                    except Exception as close_error:
                        logger.warning(f"Failed to close lock file: {close_error}")

        return _lock_context()

    def _check_file_conflict(
        self,
        target_path: Path,
        workspace_id: str,
        playbook_code: str,
        artifact_type: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        檢查檔案衝突

        檢查目標路徑是否已存在檔案，如果存在則：
        - force=False: 自動生成新版本號，建議使用新檔名
        - force=True: 返回衝突標記，允許強制覆蓋（需要前端確認）

        Args:
            target_path: 目標檔案路徑
            workspace_id: Workspace ID（用於查詢版本號）
            playbook_code: Playbook 代碼（用於查詢版本號）
            artifact_type: 產物類型（用於查詢版本號）
            force: 是否強制覆蓋（默認 False）

        Returns:
            Dict with keys:
            - has_conflict: bool, 是否存在衝突
            - suggested_version: Optional[int], Suggested version number (None if no conflict or forced overwrite)
        """
        if not target_path.exists():
            return {"has_conflict": False, "suggested_version": None}

        if force:
            logger.warning(
                f"File conflict detected at {target_path}, force=True will overwrite existing file"
            )
            return {"has_conflict": True, "suggested_version": None}

        # Auto-generate new version number
        # Extract version from filename, or query from DB
        try:
            suggested_version = self._get_next_version(
                workspace_id=workspace_id,
                playbook_code=playbook_code,
                artifact_type=artifact_type
            )
            logger.info(
                f"File conflict detected at {target_path}, "
                f"suggested version: {suggested_version}"
            )
            return {"has_conflict": True, "suggested_version": suggested_version}
        except Exception as e:
            logger.warning(
                f"Failed to get next version for conflict resolution: {e}, "
                f"falling back to timestamp-based naming"
            )
            # If version number retrieval fails, return conflict flag but no version number
            # Caller can use timestamp or other methods to generate new filename
            return {"has_conflict": True, "suggested_version": None}

    def _extract_version_from_filename(self, filename: str) -> Optional[int]:
        """
        Extract version number from filename

        Filename format: <slug>-v<number>-<timestamp>.<ext>
        Extract version number from it.

        Args:
            filename: Filename (without path)

        Returns:
            Version number (None if extraction fails)
        """
        import re
        # Match -v<number>- pattern
        match = re.search(r'-v(\d+)-', filename)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def _extract_version_from_filename(self, filename: str) -> Optional[int]:
        """
        Extract version number from filename

        Filename format: <slug>-v<number>-<timestamp>.<ext>
        Extract version number from it.

        Args:
            filename: Filename (without path)

        Returns:
            Version number (None if extraction fails)
        """
        import re
        # Match -v<number>- pattern
        match = re.search(r'-v(\d+)-', filename)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

