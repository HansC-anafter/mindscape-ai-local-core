"""
Local Folder Indexer Service

Indexes local folder content into vector database for RAG retrieval.
Supports markdown, text, and structured data files.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import hashlib

from backend.app.services.vector_search import VectorSearchService
from backend.app.services.knowledge_authorization import RetrievalAccessContext
from backend.app.services.knowledge_projection.legacy_document_facade import (
    AuthorizedLegacyDocumentFacade,
    LegacyDocumentChunk,
)

logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}


class LocalFolderIndexer:
    """
    Index local folder content for RAG retrieval.

    Scans files in a directory, chunks content, generates embeddings,
    and stores in external_docs table for semantic search.
    """

    def __init__(
        self,
        vector_service: Optional[VectorSearchService] = None,
        workspace_id: Optional[str] = None,
        access_context: Optional[RetrievalAccessContext] = None,
    ):
        """
        Initialize LocalFolderIndexer

        Args:
            vector_service: VectorSearchService instance (optional, will create if not provided)
            workspace_id: Workspace ID for metadata tagging
        """
        self.vector_service = vector_service or VectorSearchService()
        self.workspace_id = workspace_id
        self.access_context = access_context
        self.projection_facade = AuthorizedLegacyDocumentFacade(
            vector_service=self.vector_service
        )

    async def index_folder(self, folder_path: str) -> Dict[str, Any]:
        """
        Index all supported files in a folder

        Args:
            folder_path: Path to folder to index
            user_id: User ID for indexing

        Returns:
            Dictionary with indexing results
        """
        folder = Path(folder_path)

        if not folder.exists():
            logger.error(f"Folder does not exist: {folder_path}")
            return {
                "success": False,
                "error": f"Folder does not exist: {folder_path}",
                "files_indexed": 0,
            }

        if not folder.is_dir():
            logger.error(f"Path is not a directory: {folder_path}")
            return {
                "success": False,
                "error": f"Path is not a directory: {folder_path}",
                "files_indexed": 0,
            }

        # Scan for supported files
        files = self._scan_files(folder)
        logger.info(f"Found {len(files)} supported files in {folder_path}")

        indexed_count = 0
        chunk_count = 0
        errors = []

        for file_path in files:
            try:
                # Read file content
                content = self._read_file_content(file_path)
                if not content:
                    continue

                # Chunk content
                chunks = self._chunk_content(content, max_len=500)

                # Generate file hash for deduplication
                file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

                await self._save_file(
                    chunks=chunks,
                    file_path=file_path,
                    file_hash=file_hash,
                )
                chunk_count += len(chunks)

                indexed_count += 1
                logger.info(f"Indexed file: {file_path.name} ({len(chunks)} chunks)")

            except Exception as e:
                error_msg = f"Failed to index {file_path.name}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        result = {
            "success": True,
            "folder_path": str(folder_path),
            "files_found": len(files),
            "files_indexed": indexed_count,
            "chunks_created": chunk_count,
            "workspace_id": self.workspace_id,
        }

        if errors:
            result["errors"] = errors

        logger.info(f"Indexing complete: {indexed_count} files, {chunk_count} chunks")
        return result

    def _scan_files(self, folder: Path) -> List[Path]:
        """
        Scan folder for supported files

        Args:
            folder: Path to folder

        Returns:
            List of file paths
        """
        files = []

        for file_path in folder.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                # Skip hidden files and directories
                if not any(part.startswith(".") for part in file_path.parts):
                    files.append(file_path)

        return sorted(files)

    def _read_file_content(self, file_path: Path) -> Optional[str]:
        """
        Read file content

        Args:
            file_path: Path to file

        Returns:
            File content as string or None if read fails
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read file {file_path}: {e}")
            return None

    def _chunk_content(
        self, content: str, max_len: int = 500, overlap: int = 50
    ) -> List[str]:
        """
        Chunk content into smaller pieces for better retrieval

        Args:
            content: Full content string
            max_len: Maximum chunk length in characters
            overlap: Overlap between chunks

        Returns:
            List of content chunks
        """
        if len(content) <= max_len:
            return [content.strip()] if content.strip() else []

        chunks = []

        # Split by paragraphs first
        paragraphs = content.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If adding this paragraph exceeds max_len, save current chunk
            if len(current_chunk) + len(para) + 2 > max_len:
                if current_chunk:
                    chunks.append(current_chunk.strip())

                # If single paragraph is too long, split by sentences
                if len(para) > max_len:
                    sentences = para.replace(". ", ".\n").split("\n")
                    current_chunk = ""
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) + 1 > max_len:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = sentence
                        else:
                            current_chunk += (
                                " " + sentence if current_chunk else sentence
                            )
                else:
                    current_chunk = para
            else:
                current_chunk += "\n\n" + para if current_chunk else para

        # Don't forget the last chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    async def _save_file(
        self,
        chunks: List[str],
        file_path: Path,
        file_hash: str,
    ) -> None:
        if self.workspace_id is None or self.access_context is None:
            raise PermissionError("local_folder_authorized_scope_required")
        await self.projection_facade.replace_document(
            access_context=self.access_context,
            workspace_id=self.workspace_id,
            owner_capability_code="local_folder",
            source_app="local_folder",
            source_id=str(file_path.resolve()),
            doc_type="local_file",
            source_revision=hashlib.sha256(
                "\n".join(chunks).encode("utf-8")
            ).hexdigest(),
            chunks=tuple(
                LegacyDocumentChunk(
                    content=chunk,
                    title=f"{file_path.name}:chunk_{index}",
                    metadata={
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "file_hash": file_hash,
                        "chunk_index": index,
                        "total_chunks": len(chunks),
                    },
                )
                for index, chunk in enumerate(chunks)
            ),
        )

    async def get_index_status(self, folder_path: str) -> Dict[str, Any]:
        """
        Get indexing status for a folder

        Args:
            folder_path: Path to folder
            user_id: User ID

        Returns:
            Status dictionary
        """
        folder = Path(folder_path)

        # Count files in folder
        files = self._scan_files(folder) if folder.exists() else []

        if self.workspace_id is None or self.access_context is None:
            raise PermissionError("local_folder_authorized_scope_required")
        documents = self.projection_facade.list_documents(
            access_context=self.access_context,
            workspace_id=self.workspace_id,
            owner_capability_code="local_folder",
            source_app="local_folder",
            limit=200,
        )
        indexed_count = sum(int(row["chunk_count"]) for row in documents)

        return {
            "folder_path": str(folder_path),
            "folder_exists": folder.exists(),
            "files_count": len(files),
            "indexed_chunks": indexed_count,
            "workspace_id": self.workspace_id,
        }
