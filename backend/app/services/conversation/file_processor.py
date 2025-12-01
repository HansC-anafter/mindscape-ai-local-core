"""
File Processor

Processes files in chat flow, extracting file document IDs from MindEvents.
"""

import logging
from typing import List
from ...services.mindscape_store import MindscapeStore
from ...core.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


class FileProcessor:
    """
    Processes files in /chat flow

    For files that are already uploaded (file IDs), this method:
    1. Looks up file information from recent events
    2. Extracts text content if not already extracted
    3. Returns file_document_ids for reference
    """

    def __init__(self, store: MindscapeStore):
        """
        Initialize FileProcessor

        Args:
            store: MindscapeStore instance
        """
        self.store = store

    async def process_files_in_chat(
        self,
        workspace_id: str,
        profile_id: str,
        files: List[str]
    ) -> List[str]:
        """
        Process files in /chat flow

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            files: List of file IDs

        Returns:
            List of file_document_ids
        """
        ctx = ExecutionContext(
            actor_id=profile_id,
            workspace_id=workspace_id,
            tags={"mode": "local"}
        )
        return await self.process_files_in_chat_with_ctx(
            ctx=ctx,
            files=files
        )

    async def process_files_in_chat_with_ctx(
        self,
        ctx: ExecutionContext,
        files: List[str]
    ) -> List[str]:
        """
        Process files in /chat flow using ExecutionContext

        Args:
            ctx: Execution context
            files: List of file IDs

        Returns:
            List of file_document_ids
        """
        file_document_ids = []

        # Look up file information from recent events
        recent_events = self.store.get_events_by_workspace(
            workspace_id=ctx.workspace_id,
            limit=100
        )

        for file_id in files:
            # Find the most recent event with this file_id
            for event in recent_events:
                payload = event.payload if isinstance(event.payload, dict) else {}
                event_files = payload.get("files", [])

                if isinstance(event_files, list):
                    for file_info in event_files:
                        if isinstance(file_info, dict) and file_info.get("id") == file_id:
                            # Found file info in event
                            file_document_id = file_info.get("document_id") or file_info.get("file_document_id")
                            if file_document_id:
                                file_document_ids.append(file_document_id)
                                break
                        elif isinstance(file_info, str) and file_info == file_id:
                            # File ID matches, check metadata
                            metadata = event.metadata if isinstance(event.metadata, dict) else {}
                            file_document_id = metadata.get("file_document_id") or metadata.get("document_id")
                            if file_document_id:
                                file_document_ids.append(file_document_id)
                                break
                elif isinstance(event_files, str) and event_files == file_id:
                    # File ID matches, check metadata
                    metadata = event.metadata if isinstance(event.metadata, dict) else {}
                    file_document_id = metadata.get("file_document_id") or metadata.get("document_id")
                    if file_document_id:
                        file_document_ids.append(file_document_id)
                        break

                if file_document_ids and file_document_ids[-1]:
                    break

        logger.info(f"Processed {len(files)} files, found {len(file_document_ids)} document IDs")
        return file_document_ids
