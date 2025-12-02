"""
Playbook Indexer Service
Chunks Playbook markdown content and indexes it into pgvector for RAG
"""

import os
import uuid
import json
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class PlaybookIndexer:
    """Index Playbook content into pgvector for semantic search"""

    def __init__(self, postgres_config=None):
        self.postgres_config = postgres_config or self._get_postgres_config()

    def _get_postgres_config(self):
        """Get PostgreSQL config from environment"""
        return {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": os.getenv("POSTGRES_USER", "mindscape"),
            "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        }

    def _get_connection(self):
        """Get PostgreSQL connection"""
        return psycopg2.connect(**self.postgres_config)

    def chunk_markdown(
        self,
        content: str,
        max_chunk_size: int = 500,
        overlap: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Chunk Markdown content into smaller pieces

        Args:
            content: Markdown content
            max_chunk_size: Maximum characters per chunk
            overlap: Overlap between chunks

        Returns:
            List of chunks with metadata
        """
        chunks = []

        # Split by major sections (## headers)
        sections = re.split(r'\n(#{1,3})\s+', content)

        current_chunk = ""
        current_section_type = "overview"
        section_number = 0

        i = 0
        while i < len(sections):
            section_text = sections[i]

            # Check if this is a header marker
            if i + 1 < len(sections) and sections[i] in ['#', '##', '###']:
                header_level = sections[i]
                header_text = sections[i + 1] if i + 1 < len(sections) else ""

                # Extract section type from header
                section_type = self._extract_section_type(header_text)

                # If we have content, save current chunk
                if current_chunk.strip():
                    chunks.append({
                        "content": current_chunk.strip(),
                        "section_type": current_section_type,
                        "section_number": section_number,
                        "char_count": len(current_chunk)
                    })
                    section_number += 1

                # Start new chunk with header
                current_chunk = f"{header_level} {header_text}\n\n"
                current_section_type = section_type
                i += 2
            else:
                # Add to current chunk
                current_chunk += section_text

                # If chunk is too large, split it
                if len(current_chunk) > max_chunk_size:
                    # Find good split point (paragraph break)
                    split_point = self._find_split_point(current_chunk, max_chunk_size)

                    chunks.append({
                        "content": current_chunk[:split_point].strip(),
                        "section_type": current_section_type,
                        "section_number": section_number,
                        "char_count": split_point
                    })
                    section_number += 1

                    # Keep overlap for context
                    current_chunk = current_chunk[split_point - overlap:]

                i += 1

        # Add final chunk
        if current_chunk.strip():
            chunks.append({
                "content": current_chunk.strip(),
                "section_type": current_section_type,
                "section_number": section_number,
                "char_count": len(current_chunk)
            })

        logger.info(f"Chunked content into {len(chunks)} pieces")
        return chunks

    def _extract_section_type(self, header_text: str) -> str:
        """Extract section type from header text"""
        header_lower = header_text.lower()

        if any(word in header_lower for word in ['目標', '目的', 'goal', 'objective']):
            return 'overview'
        elif any(word in header_lower for word in ['步驟', 'step', '流程', 'process']):
            return 'step'
        elif any(word in header_lower for word in ['範例', 'example', '示例']):
            return 'example'
        elif any(word in header_lower for word in ['提示', 'tip', '建議', 'advice']):
            return 'tips'
        elif any(word in header_lower for word in ['前提', 'prerequisite', '準備']):
            return 'prerequisite'
        else:
            return 'content'

    def _find_split_point(self, text: str, max_size: int) -> int:
        """Find good split point (paragraph or sentence boundary)"""
        # Try to split at paragraph break
        for i in range(max_size, max(0, max_size - 200), -1):
            if i < len(text) and text[i:i+2] == '\n\n':
                return i

        # Try to split at sentence break
        for i in range(max_size, max(0, max_size - 100), -1):
            if i < len(text) and text[i] in '.!?。！？':
                return i + 1

        # Default to max_size
        return min(max_size, len(text))

    async def index_playbook(
        self,
        playbook_code: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> int:
        """
        Index a Playbook's content into pgvector

        Args:
            playbook_code: Playbook identifier
            content: Markdown content
            metadata: Additional metadata (version, tags, agent_type, etc.)

        Returns:
            Number of chunks indexed
        """
        try:
            # First, delete existing chunks for this playbook
            self._delete_existing_chunks(playbook_code)

            # Chunk the content
            chunks = self.chunk_markdown(content)

            # Generate embeddings and save each chunk
            indexed_count = 0
            for chunk in chunks:
                embedding = await self._generate_embedding(chunk["content"])

                if embedding:
                    chunk_metadata = {
                        **(metadata or {}),
                        "section_number": chunk["section_number"],
                        "char_count": chunk["char_count"]
                    }

                    self._save_chunk(
                        playbook_code=playbook_code,
                        section_type=chunk["section_type"],
                        content=chunk["content"],
                        embedding=embedding,
                        metadata=chunk_metadata
                    )
                    indexed_count += 1
                else:
                    logger.warning(f"Failed to generate embedding for chunk {chunk['section_number']}")

            logger.info(f"Indexed {indexed_count}/{len(chunks)} chunks for playbook {playbook_code}")
            return indexed_count

        except Exception as e:
            logger.error(f"Failed to index playbook {playbook_code}: {e}", exc_info=True)
            return 0

    def _delete_existing_chunks(self, playbook_code: str):
        """Delete existing chunks for a playbook"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM playbook_knowledge
                WHERE playbook_code = %s
            ''', (playbook_code,))
            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"Deleted {deleted_count} existing chunks for playbook {playbook_code}")
        finally:
            conn.close()

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using OpenAI"""
        try:
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                logger.warning("OPENAI_API_KEY not set, skipping embedding")
                return None

            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.embeddings.create(
                model="text-embedding-3-small",  # 1536 dimensions
                input=text
            )
            return response.data[0].embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    def _save_chunk(
        self,
        playbook_code: str,
        section_type: str,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any]
    ):
        """Save a chunk to PostgreSQL"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            chunk_id = str(uuid.uuid4())

            cursor.execute('''
                INSERT INTO playbook_knowledge (
                    id, playbook_code, section_type, content,
                    embedding, metadata, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s)
            ''', (
                chunk_id,
                playbook_code,
                section_type,
                content,
                str(embedding),
                json.dumps(metadata),
                datetime.utcnow(),
                datetime.utcnow()
            ))

            conn.commit()
        finally:
            conn.close()

    async def reindex_all_playbooks(self, playbooks_dir: str = "docs/playbooks") -> Dict[str, Any]:
        """
        Reindex all Playbooks from the playbooks directory

        Returns:
            Statistics about the indexing process
        """
        from pathlib import Path

        playbooks_path = Path(playbooks_dir)
        if not playbooks_path.exists():
            raise FileNotFoundError(f"Playbooks directory not found: {playbooks_dir}")

        stats = {
            "total_playbooks": 0,
            "indexed_playbooks": 0,
            "total_chunks": 0,
            "failed": []
        }

        # Find all markdown files (excluding README)
        markdown_files = [f for f in playbooks_path.glob("*.md") if f.name != "README.md"]
        stats["total_playbooks"] = len(markdown_files)

        for md_file in markdown_files:
            try:
                # Read file content
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Extract playbook_code from frontmatter
                import yaml
                frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
                if not frontmatter_match:
                    logger.warning(f"No frontmatter found in {md_file.name}")
                    continue

                frontmatter_text = frontmatter_match.group(1)
                markdown_content = frontmatter_match.group(2)

                frontmatter = yaml.safe_load(frontmatter_text)
                playbook_code = frontmatter.get('playbook_code')

                if not playbook_code:
                    logger.warning(f"No playbook_code in {md_file.name}")
                    stats["failed"].append(md_file.name)
                    continue

                # Index the playbook
                metadata = {
                    "version": frontmatter.get('version', '1.0.0'),
                    "agent_type": frontmatter.get('entry_agent_type'),
                    "tags": frontmatter.get('tags', [])
                }

                chunk_count = await self.index_playbook(
                    playbook_code=playbook_code,
                    content=markdown_content,
                    metadata=metadata
                )

                stats["indexed_playbooks"] += 1
                stats["total_chunks"] += chunk_count

                logger.info(f"✓ Indexed {playbook_code}: {chunk_count} chunks")

            except Exception as e:
                logger.error(f"Failed to index {md_file.name}: {e}")
                stats["failed"].append(md_file.name)

        logger.info(f"Reindexing complete: {stats['indexed_playbooks']}/{stats['total_playbooks']} playbooks, {stats['total_chunks']} chunks")
        return stats
