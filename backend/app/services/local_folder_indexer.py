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
    ):
        """
        Initialize LocalFolderIndexer

        Args:
            vector_service: VectorSearchService instance (optional, will create if not provided)
            workspace_id: Workspace ID for metadata tagging
        """
        self.vector_service = vector_service or VectorSearchService()
        self.workspace_id = workspace_id

    async def index_folder(
        self, folder_path: str, user_id: str = "system"
    ) -> Dict[str, Any]:
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
                file_hash = hashlib.md5(content.encode()).hexdigest()

                # Save each chunk
                for i, chunk in enumerate(chunks):
                    success = await self._save_chunk(
                        chunk=chunk,
                        file_path=file_path,
                        chunk_index=i,
                        total_chunks=len(chunks),
                        file_hash=file_hash,
                        user_id=user_id,
                    )
                    if success:
                        chunk_count += 1

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

    async def _save_chunk(
        self,
        chunk: str,
        file_path: Path,
        chunk_index: int,
        total_chunks: int,
        file_hash: str,
        user_id: str,
    ) -> bool:
        """
        Save a chunk to external_docs

        Args:
            chunk: Content chunk
            file_path: Source file path
            chunk_index: Index of this chunk
            total_chunks: Total number of chunks
            file_hash: MD5 hash of full file content
            user_id: User ID

        Returns:
            True if successful
        """
        # Generate embedding with model info
        embedding, model_name = (
            await self.vector_service._generate_embedding_with_model(chunk)
        )
        if not embedding:
            logger.warning(
                f"Failed to generate embedding for chunk {chunk_index} of {file_path.name}"
            )
            return False

        # Build metadata with embedding model info
        metadata = {
            "file_name": file_path.name,
            "file_path": str(file_path),
            "file_hash": file_hash,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "workspace_id": self.workspace_id,
            "embedding_model": model_name,
            "embedding_dimension": len(embedding),
        }

        # Create unique title for deduplication
        title = f"{file_path.name}:chunk_{chunk_index}"
        if self.workspace_id:
            title = f"{self.workspace_id}:{title}"

        # Save to external_docs
        doc = {
            "user_id": user_id,
            "source_app": "local_folder",
            "title": title,
            "content": chunk,
            "embedding": embedding,
            "metadata": metadata,
        }

        return await self.vector_service.save_to_external_docs(doc)

    async def get_index_status(
        self, folder_path: str, user_id: str = "system"
    ) -> Dict[str, Any]:
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

        # Count indexed documents
        conn = self.vector_service._get_connection()
        try:
            cursor = conn.cursor()

            # Count documents for this workspace
            where_clause = "source_app = 'local_folder'"
            params = []

            if self.workspace_id:
                where_clause += " AND metadata::text LIKE %s"
                params.append(f'%"workspace_id": "{self.workspace_id}"%')

            cursor.execute(
                f"SELECT COUNT(*) FROM external_docs WHERE {where_clause}", params
            )
            indexed_count = cursor.fetchone()[0]

        finally:
            conn.close()

        return {
            "folder_path": str(folder_path),
            "folder_exists": folder.exists(),
            "files_count": len(files),
            "indexed_chunks": indexed_count,
            "workspace_id": self.workspace_id,
        }
