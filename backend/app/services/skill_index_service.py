"""
Skill Index Service

Indexes SKILL.md files from capability packs for semantic search during planning.
Enables PlanBuilder to discover relevant capabilities based on user intent.

Features:
- Parses SKILL.md frontmatter and content
- Generates embeddings for skill descriptions
- Vector search for capability discovery
- Integration with PlanBuilder
"""

import os
import re
import yaml
import logging
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SkillDocument:
    """Represents a parsed SKILL.md document"""

    pack_code: str
    name: str
    description: str
    skills: List[Dict[str, str]]  # [{skill: str, description: str}]
    tools: List[Dict[str, str]]  # [{tool: str, purpose: str}]
    categories: List[str]
    file_path: str
    content_hash: str
    embedding: Optional[List[float]] = None

    def to_embedding_text(self) -> str:
        """Generate text for embedding"""
        parts = [
            f"Pack: {self.name}",
            f"Description: {self.description}",
        ]

        if self.skills:
            skills_text = ", ".join(s.get("skill", "") for s in self.skills[:5])
            parts.append(f"Skills: {skills_text}")

        if self.tools:
            tools_text = ", ".join(t.get("tool", "") for t in self.tools[:5])
            parts.append(f"Tools: {tools_text}")

        if self.categories:
            parts.append(f"Categories: {', '.join(self.categories)}")

        return "\n".join(parts)


class SkillIndexService:
    """
    Service for indexing and searching SKILL.md files
    """

    def __init__(
        self,
        store=None,
        embedding_provider: str = "ollama",
        capabilities_dir: Optional[str] = None,
    ):
        self.store = store
        self.embedding_provider = embedding_provider
        self.capabilities_dir = capabilities_dir
        self._skill_cache: Dict[str, SkillDocument] = {}
        self._embeddings_dirty = False

    def _parse_skill_md(self, file_path: Path) -> Optional[SkillDocument]:
        """
        Parse a SKILL.md file into structured SkillDocument

        Extracts:
        - Pack name from frontmatter or first heading
        - Description from subtitle
        - Skills table
        - Tools table
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

            pack_code = file_path.parent.name

            # Extract name from first heading
            name_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            name = name_match.group(1).strip() if name_match else pack_code

            # Extract description from subtitle (> quote)
            desc_match = re.search(r"^>\s+(.+)$", content, re.MULTILINE)
            description = desc_match.group(1).strip() if desc_match else ""

            # Extract skills from "Skills" section tables
            skills = self._parse_skill_table(content)

            # Extract tools from "Tools" section tables
            tools = self._parse_tools_table(content)

            # Extract categories from "What This Pack Can Do" section
            categories = self._parse_categories(content)

            return SkillDocument(
                pack_code=pack_code,
                name=name,
                description=description,
                skills=skills,
                tools=tools,
                categories=categories,
                file_path=str(file_path),
                content_hash=content_hash,
            )

        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None

    def _parse_skill_table(self, content: str) -> List[Dict[str, str]]:
        """Parse skills from markdown tables"""
        skills = []

        # Match table rows with skill patterns
        # | `pack.skill_name` | Description |
        pattern = r"\|\s*`?([a-z_]+\.[a-z_]+)`?\s*\|\s*(.+?)\s*\|"
        matches = re.findall(pattern, content, re.IGNORECASE)

        for skill, desc in matches:
            skills.append({"skill": skill.strip(), "description": desc.strip()})

        # Also match simpler patterns
        # | Skill Name | Description |
        simple_pattern = r"\|\s*([A-Za-z][^\|]+)\s*\|\s*([^\|]+)\s*\|"
        for row in re.findall(simple_pattern, content):
            skill_name = row[0].strip()
            if skill_name and skill_name.lower() not in ("skill", "category", "---"):
                skills.append({"skill": skill_name, "description": row[1].strip()})

        return skills[:20]  # Limit to 20 skills

    def _parse_tools_table(self, content: str) -> List[Dict[str, str]]:
        """Parse tools from markdown tables"""
        tools = []

        # Match tool patterns
        # | `tool_name` | Purpose |
        pattern = r"\|\s*`?([a-z_]+)`?\s*\|\s*(.+?)\s*\|"

        # Find Tools section
        tools_section = re.search(
            r"##\s+Tools.*?\n(.*?)(?=\n##|\n---|\Z)", content, re.IGNORECASE | re.DOTALL
        )

        if tools_section:
            matches = re.findall(pattern, tools_section.group(1), re.IGNORECASE)
            for tool, purpose in matches:
                if tool.lower() not in ("tool", "code", "---"):
                    tools.append({"tool": tool.strip(), "purpose": purpose.strip()})

        return tools[:20]

    def _parse_categories(self, content: str) -> List[str]:
        """Parse categories from 'What This Pack Can Do' section"""
        categories = []

        # Match category patterns from table
        # | **Category** | Skills |
        pattern = r"\|\s*\*\*(.+?)\*\*\s*\|"
        matches = re.findall(pattern, content)

        for cat in matches:
            if cat.strip().lower() not in ("category", "---"):
                categories.append(cat.strip())

        return categories[:10]

    async def index_capabilities(
        self,
        capabilities_dirs: Optional[List[str]] = None,
        force_reindex: bool = False,
    ) -> Dict[str, Any]:
        """
        Index all SKILL.md files from capability directories

        Args:
            capabilities_dirs: List of directories to scan
            force_reindex: Force reindex even if cached

        Returns:
            {"indexed": int, "skipped": int, "errors": int}
        """
        if not capabilities_dirs:
            # Default directories
            capabilities_dirs = []

            # Local capabilities
            local_caps = Path(__file__).parent.parent.parent / "capabilities"
            if local_caps.exists():
                capabilities_dirs.append(str(local_caps))

            # Cloud capabilities (if accessible)
            cloud_caps = (
                Path.home() / "Projects_local/workspace/mindscape-ai-cloud/capabilities"
            )
            if cloud_caps.exists():
                capabilities_dirs.append(str(cloud_caps))

        stats = {"indexed": 0, "skipped": 0, "errors": 0}

        for caps_dir in capabilities_dirs:
            caps_path = Path(caps_dir)
            if not caps_path.exists():
                continue

            for skill_file in caps_path.glob("*/SKILL.md"):
                try:
                    pack_code = skill_file.parent.name

                    # Check cache
                    if not force_reindex and pack_code in self._skill_cache:
                        cached = self._skill_cache[pack_code]
                        current_hash = hashlib.sha256(
                            skill_file.read_text().encode()
                        ).hexdigest()[:16]

                        if cached.content_hash == current_hash:
                            stats["skipped"] += 1
                            continue

                    # Parse and index
                    doc = self._parse_skill_md(skill_file)
                    if doc:
                        self._skill_cache[pack_code] = doc
                        self._embeddings_dirty = True
                        stats["indexed"] += 1
                    else:
                        stats["errors"] += 1

                except Exception as e:
                    logger.error(f"Failed to index {skill_file}: {e}")
                    stats["errors"] += 1

        logger.info(
            f"Skill index: {stats['indexed']} indexed, "
            f"{stats['skipped']} skipped, {stats['errors']} errors"
        )

        return stats

    async def generate_embeddings(self) -> int:
        """
        Generate embeddings for all indexed skills

        Returns:
            Number of embeddings generated
        """
        if not self._embeddings_dirty:
            return 0

        count = 0

        for pack_code, doc in self._skill_cache.items():
            if doc.embedding is None:
                text = doc.to_embedding_text()
                embedding = await self._generate_embedding(text)
                if embedding:
                    doc.embedding = embedding
                    count += 1

        self._embeddings_dirty = False
        logger.info(f"Generated {count} skill embeddings")
        return count

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding using configured provider"""
        try:
            if self.embedding_provider == "ollama":
                return await self._embed_ollama(text)
            elif self.embedding_provider == "openai":
                return await self._embed_openai(text)
            else:
                logger.warning(f"Unknown provider: {self.embedding_provider}")
                return None
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return None

    async def _embed_ollama(self, text: str) -> Optional[List[float]]:
        """Generate embedding using Ollama"""
        import httpx

        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ollama_url}/api/embeddings", json={"model": model, "prompt": text}
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("embedding")

        return None

    async def _embed_openai(self, text: str) -> Optional[List[float]]:
        """Generate embedding using OpenAI (BYOK)"""
        import httpx

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set")
            return None

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "text-embedding-3-small",
                    "input": text,
                },
            )

            if response.status_code == 200:
                data = response.json()
                return data["data"][0]["embedding"]

        return None

    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.5,
    ) -> List[Tuple[SkillDocument, float]]:
        """
        Search for relevant capabilities by query

        Args:
            query: User query/intent
            top_k: Number of results
            min_score: Minimum similarity score

        Returns:
            List of (SkillDocument, score) tuples
        """
        # Generate query embedding
        query_embedding = await self._generate_embedding(query)
        if not query_embedding:
            # Fallback to keyword search
            return self._keyword_search(query, top_k)

        # Compute similarities
        results = []
        for pack_code, doc in self._skill_cache.items():
            if doc.embedding:
                score = self._cosine_similarity(query_embedding, doc.embedding)
                if score >= min_score:
                    results.append((doc, score))

        # Sort by score
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _keyword_search(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Tuple[SkillDocument, float]]:
        """Fallback keyword-based search"""
        query_words = set(query.lower().split())
        results = []

        for pack_code, doc in self._skill_cache.items():
            text = doc.to_embedding_text().lower()
            score = sum(1 for w in query_words if w in text) / max(len(query_words), 1)
            if score > 0:
                results.append((doc, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors"""
        import math

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    def get_capability_suggestions(self, query: str) -> List[Dict[str, Any]]:
        """
        Get capability suggestions for PlanBuilder integration

        Args:
            query: User message/intent

        Returns:
            List of suggested capabilities with metadata
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        results = loop.run_until_complete(self.search(query))

        suggestions = []
        for doc, score in results:
            suggestions.append(
                {
                    "pack_code": doc.pack_code,
                    "name": doc.name,
                    "description": doc.description,
                    "score": round(score, 3),
                    "skills": [s.get("skill") for s in doc.skills[:3]],
                    "tools": [t.get("tool") for t in doc.tools[:3]],
                }
            )

        return suggestions

    def list_all_capabilities(self) -> List[Dict[str, Any]]:
        """List all indexed capabilities"""
        return [
            {
                "pack_code": doc.pack_code,
                "name": doc.name,
                "description": doc.description,
                "skill_count": len(doc.skills),
                "tool_count": len(doc.tools),
                "categories": doc.categories,
            }
            for doc in self._skill_cache.values()
        ]


# Singleton instance
_skill_index_service: Optional[SkillIndexService] = None


def get_skill_index_service() -> SkillIndexService:
    """Get or create SkillIndexService singleton"""
    global _skill_index_service
    if _skill_index_service is None:
        _skill_index_service = SkillIndexService()
    return _skill_index_service
