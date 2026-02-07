"""
File Analysis Service

Handles file upload, analysis, and timeline/task creation.
Extracted from workspace routes for better separation of concerns.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.multi_ai_collaboration import MultiAICollaborationService
from backend.app.services.i18n_service import get_i18n_service
from backend.app.shared.i18n_loader import get_locale_from_context

logger = logging.getLogger(__name__)


class FileAnalysisService:
    """Service for file upload and analysis"""

    def __init__(
        self,
        store: MindscapeStore,
        timeline_items_store: TimelineItemsStore,
        tasks_store: TasksStore,
    ):
        """
        Initialize FileAnalysisService

        Args:
            store: MindscapeStore instance
            timeline_items_store: TimelineItemsStore instance
            tasks_store: TasksStore instance
        """
        self.store = store
        self.timeline_items_store = timeline_items_store
        self.tasks_store = tasks_store
        self.collaboration_service = MultiAICollaborationService()

    async def _get_i18n_message(
        self, workspace_id: str, module: str, key: str, **kwargs
    ) -> str:
        """Get i18n message with locale from workspace context"""
        workspace = None
        try:
            workspace = await self.store.get_workspace(workspace_id)
        except Exception:
            pass

        locale = get_locale_from_context(workspace=workspace) or "en"
        i18n = get_i18n_service(default_locale=locale)
        return i18n.t(module, key, **kwargs)

    async def upload_file(
        self,
        workspace_id: str,
        file_data: str,
        file_name: str,
        file_type: Optional[str],
        file_size: Optional[int],
    ) -> Dict[str, Any]:
        """
        Upload file to storage

        Args:
            workspace_id: Workspace ID
            file_data: Base64 encoded file data (data URL format)
            file_name: File name
            file_type: File MIME type
            file_size: File size in bytes

        Returns:
            Dict with file_id and file_path
        """
        if not file_data or not file_data.startswith("data:"):
            raise ValueError("Invalid file_data format, expected base64 data URL")

        import base64
        import os
        from pathlib import Path

        header, encoded = file_data.split(",", 1)
        file_content = base64.b64decode(encoded)

        import hashlib

        file_hash = hashlib.sha256(file_content).hexdigest()

        file_id = str(uuid.uuid4())

        uploads_dir = os.getenv("UPLOADS_DIR", "data/uploads")
        workspace_uploads_dir = Path(uploads_dir) / workspace_id
        workspace_uploads_dir.mkdir(parents=True, exist_ok=True)

        file_ext = Path(file_name).suffix if file_name else ""
        if not file_ext:
            if file_type:
                mime_to_ext = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/gif": ".gif",
                    "application/pdf": ".pdf",
                    "text/plain": ".txt",
                    "application/json": ".json",
                }
                file_ext = mime_to_ext.get(file_type, "")

        file_path = workspace_uploads_dir / f"{file_id}{file_ext}"
        with open(file_path, "wb") as f:
            f.write(file_content)

        logger.info(f"Uploaded file: {file_name} -> {file_path} (file_id: {file_id})")

        return {
            "file_id": file_id,
            "file_path": str(file_path),
            "file_name": file_name,
            "file_type": file_type,
            "file_size": file_size or len(file_content),
            "file_hash": file_hash,
        }

    async def analyze_file(
        self,
        workspace_id: str,
        profile_id: str,
        file_id: Optional[str],
        file_data: Optional[str],
        file_name: str,
        file_type: Optional[str],
        file_size: Optional[int],
        file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze uploaded file with multiple AI capabilities

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            file_id: File ID from upload (preferred)
            file_data: Base64 encoded file data (fallback)
            file_name: File name
            file_type: File MIME type
            file_size: File size in bytes
            file_path: File path on server (optional)

        Returns:
            Analysis result with file_id, file_path, and collaboration_results
        """
        logger.info(
            f"Starting file analysis for {file_name} (file_id={file_id}, has_file_data={bool(file_data)}, file_path={file_path})"
        )

        if not file_id and not file_data:
            raise ValueError("Either file_id or file_data is required")

        if not file_path and file_id:
            try:
                from backend.app.capabilities.core_files.services.upload import (
                    get_file_path_by_id,
                )

                file_path = get_file_path_by_id(file_id)
            except (ImportError, AttributeError):
                from pathlib import Path
                import os

                uploads_dir = os.getenv("UPLOADS_DIR", "data/uploads")
                uploads_path = Path(uploads_dir)
                if uploads_path.exists():
                    for uploaded_file in uploads_path.rglob(f"{file_id}.*"):
                        file_path = str(uploaded_file)
                        logger.info(
                            f"Found file_path for file_id {file_id}: {file_path}"
                        )
                        break
                    if not file_path:
                        logger.warning(
                            f"Could not find file_path for file_id {file_id} in {uploads_path}"
                        )

        logger.info(f"Calling collaboration_service.analyze_file for {file_name}")
        try:
            analysis_result = await self.collaboration_service.analyze_file(
                file_data=file_data or file_id or "",
                file_name=file_name,
                file_type=file_type,
                file_size=file_size,
                profile_id=profile_id,
                workspace_id=workspace_id,
                file_path=file_path,
            )
            logger.info(f"Collaboration service analysis completed for {file_name}")
        except Exception as e:
            logger.error(
                f"Failed to analyze file {file_name} with collaboration service: {e}",
                exc_info=True,
            )
            raise

        file_hash = None
        if file_path:
            from pathlib import Path

            if Path(file_path).exists():
                import hashlib

                try:
                    with open(file_path, "rb") as f:
                        file_content = f.read()
                        file_hash = hashlib.sha256(file_content).hexdigest()
                        logger.info(
                            f"Calculated file_hash for {file_name} from file_path: {file_hash[:16]}..."
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to calculate file_hash from file_path {file_path}: {e}"
                    )
            else:
                logger.warning(f"File path does not exist: {file_path}")
        elif file_data:
            import hashlib
            import base64

            try:
                header, encoded = file_data.split(",", 1)
                file_content = base64.b64decode(encoded)
                file_hash = hashlib.sha256(file_content).hexdigest()
                logger.info(
                    f"Calculated file_hash for {file_name} from file_data: {file_hash[:16]}..."
                )
            except Exception as e:
                logger.warning(f"Failed to calculate file_hash from file_data: {e}")
        elif file_id:
            import hashlib
            from pathlib import Path
            import os

            uploads_dir = os.getenv("UPLOADS_DIR", "data/uploads")
            uploads_path = (
                Path(uploads_dir) / workspace_id if workspace_id else Path(uploads_dir)
            )
            if uploads_path.exists():
                for uploaded_file in uploads_path.rglob(f"{file_id}.*"):
                    try:
                        with open(uploaded_file, "rb") as f:
                            file_content = f.read()
                            file_hash = hashlib.sha256(file_content).hexdigest()
                            logger.info(
                                f"Calculated file_hash for {file_name} from file_id {file_id}: {file_hash[:16]}..."
                            )
                            file_path = str(uploaded_file)
                            break
                    except Exception as e:
                        logger.warning(
                            f"Failed to calculate file_hash from file {uploaded_file}: {e}"
                        )
                        continue
                if not file_hash:
                    logger.warning(
                        f"Could not find file for file_id {file_id} in {uploads_path}"
                    )

        file_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.USER,
            channel="api",
            profile_id=profile_id,
            project_id=None,
            workspace_id=workspace_id,
            event_type=EventType.MESSAGE,
            payload={
                "message": await self._get_i18n_message(
                    workspace_id, "workspace", "file.uploaded", file_name=file_name
                ),
                "files": [{"name": file_name, "type": file_type, "size": file_size}],
            },
            entity_ids=[],
            metadata={
                "file_analysis": analysis_result,
                "should_embed": True,
                "is_artifact": True,
                "file_hash": file_hash,
                "file_name": file_name,
            },
        )
        self.store.create_event(file_event, generate_embedding=True)

        if file_path:
            analysis_result["file_path"] = file_path
        analysis_result["event_id"] = file_event.id
        analysis_result["file_id"] = file_id or file_event.id

        await self._create_intents_from_analysis(
            workspace_id=workspace_id,
            profile_id=profile_id,
            analysis_result=analysis_result,
            file_name=file_name,
        )

        await self._create_timeline_item_from_analysis(
            workspace_id=workspace_id,
            message_id=file_event.id,
            analysis_result=analysis_result,
            file_name=file_name,
        )

        return analysis_result

    async def _create_intents_from_analysis(
        self,
        workspace_id: str,
        profile_id: str,
        analysis_result: Dict[str, Any],
        file_name: str,
    ) -> None:
        """Create Intent objects from extracted semantic seeds"""
        try:
            collaboration = analysis_result.get("collaboration_results", {})
            semantic_seeds = collaboration.get("semantic_seeds", {})

            if semantic_seeds.get("enabled") and semantic_seeds.get("intents"):
                intents = semantic_seeds.get("intents", [])
                from backend.app.models.mindscape import (
                    IntentCard,
                    IntentStatus,
                    PriorityLevel,
                )
                from datetime import datetime as dt

                for intent_text in intents[:3]:
                    if intent_text and len(intent_text.strip()) > 0:
                        try:
                            existing_intents = self.store.list_intents(
                                profile_id=profile_id, status=None, priority=None
                            )

                            intent_exists = any(
                                intent.title == intent_text.strip()
                                or intent_text.strip() in intent.title
                                for intent in existing_intents
                            )

                            if not intent_exists:
                                now = dt.utcnow()
                                new_intent = IntentCard(
                                    id=str(uuid.uuid4()),
                                    profile_id=profile_id,
                                    title=intent_text.strip(),
                                    description=await self._get_i18n_message(
                                        workspace_id,
                                        "workspace",
                                        "file.intent_extracted",
                                        file_name=file_name,
                                    ),
                                    status=IntentStatus.ACTIVE,
                                    priority=PriorityLevel.MEDIUM,
                                    tags=[],
                                    category="file_extraction",
                                    progress_percentage=0.0,
                                    created_at=now,
                                    updated_at=now,
                                    started_at=None,
                                    completed_at=None,
                                    due_date=None,
                                    parent_intent_id=None,
                                    child_intent_ids=[],
                                    metadata={
                                        "source": "file_upload",
                                        "source_file": file_name,
                                        "workspace_id": workspace_id,
                                        "extracted_at": now.isoformat(),
                                    },
                                )
                                self.store.create_intent(new_intent)
                                logger.info(
                                    f"Created intent from file analysis: {intent_text[:50]}"
                                )
                        except Exception as e:
                            logger.warning(
                                f"Failed to create intent from file analysis: {e}",
                                exc_info=True,
                            )
        except Exception as e:
            logger.warning(f"Failed to process intents from file analysis: {e}")

    async def _create_timeline_item_from_analysis(
        self,
        workspace_id: str,
        message_id: str,
        analysis_result: Dict[str, Any],
        file_name: str,
    ) -> None:
        """Create TimelineItem from file analysis results"""
        try:
            from backend.app.models.workspace import TimelineItem, TimelineItemType

            collaboration = analysis_result.get("collaboration_results", {})
            semantic_seeds = collaboration.get("semantic_seeds", {})

            intents = (
                semantic_seeds.get("intents", [])
                if semantic_seeds.get("enabled")
                else []
            )

            if isinstance(file_name, list):
                file_count = len(file_name)
                file_display = f"{file_count} file(s)"
            else:
                file_count = 1
                file_display = file_name

            if intents:
                title = f"Extracted {len(intents)} intents from {file_display}"
                summary = (
                    f"Found {len(intents)} potential intents: {', '.join(intents[:3])}"
                )
            else:
                title = f"Extracted 0 intents from {file_display}"
                summary = f"Found 0 potential intents or projects"

            timeline_item = TimelineItem(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                message_id=message_id,
                task_id=None,
                type=TimelineItemType.INTENT_SEEDS,
                title=title,
                summary=summary,
                data={
                    "file_name": (
                        file_display if isinstance(file_name, list) else file_name
                    ),
                    "intents": intents[:5],
                    "themes": (
                        semantic_seeds.get("themes", [])[:5]
                        if semantic_seeds.get("themes")
                        else []
                    ),
                    "enabled": semantic_seeds.get("enabled", False),
                    "reason": (
                        semantic_seeds.get("reason")
                        if not semantic_seeds.get("enabled")
                        else None
                    ),
                },
                cta=(
                    [
                        {
                            "label": "Add to Mindscape",
                            "action": "add_to_intents",
                            "pack_id": "semantic_seeds",
                        }
                    ]
                    if semantic_seeds.get("enabled") and intents
                    else None
                ),
                created_at=datetime.utcnow(),
            )
            self.timeline_items_store.create_timeline_item(timeline_item)
            logger.info(
                f"Created timeline item from file analysis: {timeline_item.id} (intents: {len(intents)})"
            )
        except Exception as e:
            logger.error(
                f"Failed to create timeline item from file analysis: {e}", exc_info=True
            )
