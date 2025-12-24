"""
Content Reuse System for IG Post

Manages content transformation and reuse across different IG formats:
- Long article → 7-slide carousel
- Carousel → 1 reel
- Reel → 3 stories
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import yaml
import re

from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class ContentReuse:
    """
    Manages content transformation and reuse

    Supports:
    - Long article to carousel conversion
    - Carousel to reel conversion
    - Reel to stories conversion
    - Content chunking and restructuring
    """

    def __init__(self, workspace_storage: WorkspaceStorage):
        """
        Initialize Content Reuse System

        Args:
            workspace_storage: WorkspaceStorage instance
        """
        self.storage = workspace_storage

    def _resolve_post_path(self, post_path: str) -> Path:
        """
        Resolve post_path to actual file path

        Args:
            post_path: Post path (may be Obsidian-style or new format)

        Returns:
            Resolved Path object
        """
        # Handle Obsidian-style paths (e.g., "20-Posts/2025-12-23_post-slug/post.md")
        # or new format (e.g., "post-slug/post.md")
        if post_path.startswith("20-Posts/") or post_path.startswith("posts/"):
            parts = post_path.split("/")
            if len(parts) >= 2:
                post_folder = parts[-2]
                post_file = parts[-1] if parts[-1].endswith(".md") else "post.md"
            else:
                post_folder = parts[0].replace(".md", "")
                post_file = "post.md"
        else:
            # Assume it's a post slug or folder name
            post_folder = post_path.replace(".md", "").replace("/", "")
            post_file = "post.md"

        # Extract post slug from folder name (format: YYYY-MM-DD_post-slug or post-slug)
        if "_" in post_folder:
            post_slug = post_folder.split("_")[-1]
        else:
            post_slug = post_folder

        # Get post path from storage
        post_dir = self.storage.get_post_path(post_slug)
        return post_dir / post_file

    def _get_target_dir(self, target_folder: str) -> Path:
        """
        Get target directory for generated posts

        Args:
            target_folder: Target folder name (relative to posts directory)

        Returns:
            Target directory Path
        """
        # If target_folder is a full path, extract folder name
        if "/" in target_folder:
            folder_name = target_folder.split("/")[-1]
        else:
            folder_name = target_folder

        # Create target directory under posts
        target_dir = self.storage.get_posts_path() / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def article_to_carousel(
        self,
        source_post_path: str,
        target_folder: str,
        carousel_slides: int = 7,
        slide_structure: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Convert long article to carousel format

        Args:
            source_post_path: Path to source article (relative to workspace or Obsidian-style)
            target_folder: Target folder for carousel posts
            carousel_slides: Number of carousel slides (default: 7)
            slide_structure: Custom slide structure configuration (optional)

        Returns:
            Dictionary with created carousel posts information
        """
        full_source_path = self._resolve_post_path(source_post_path)

        if not full_source_path.exists():
            raise FileNotFoundError(f"Source post not found: {source_post_path}")

        frontmatter, content = self._read_markdown_file(full_source_path)

        content_chunks = self._chunk_content(content, carousel_slides)

        target_dir = self._get_target_dir(target_folder)

        created_posts = []

        for i, chunk in enumerate(content_chunks, 1):
            slide_frontmatter = frontmatter.copy()
            slide_frontmatter["type"] = "carousel"
            slide_frontmatter["status"] = "draft"
            slide_frontmatter["rev"] = "1.0"
            slide_frontmatter["created_at"] = datetime.now().isoformat()
            slide_frontmatter["updated_at"] = datetime.now().isoformat()

            slide_frontmatter["carousel_slide_number"] = i
            slide_frontmatter["carousel_total_slides"] = carousel_slides
            slide_frontmatter["source_post"] = source_post_path
            slide_frontmatter["content_reuse_type"] = "article_to_carousel"

            slide_filename = f"carousel_slide_{i:02d}.md"
            slide_path = target_dir / slide_filename

            self._write_markdown_file(slide_path, slide_frontmatter, chunk)

            created_posts.append({
                "slide_number": i,
                "path": str(slide_path.relative_to(self.storage.get_capability_root())),
                "content_preview": chunk[:100] + "..." if len(chunk) > 100 else chunk
            })

        return {
            "source_post": source_post_path,
            "target_folder": target_folder,
            "total_slides": carousel_slides,
            "created_posts": created_posts
        }

    def carousel_to_reel(
        self,
        carousel_posts: List[str],
        target_folder: str,
        reel_duration: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Convert carousel posts to reel format

        Args:
            carousel_posts: List of carousel post paths (relative to workspace or Obsidian-style)
            target_folder: Target folder for reel post
            reel_duration: Reel duration in seconds (optional)

        Returns:
            Dictionary with created reel post information
        """
        if not carousel_posts:
            raise ValueError("carousel_posts list cannot be empty")

        combined_content = []
        base_frontmatter = None

        for post_path in carousel_posts:
            full_path = self._resolve_post_path(post_path)

            if not full_path.exists():
                logger.warning(f"Carousel post not found: {post_path}")
                continue

            frontmatter, content = self._read_markdown_file(full_path)

            if base_frontmatter is None:
                base_frontmatter = frontmatter.copy()

            combined_content.append(f"## Slide {frontmatter.get('carousel_slide_number', '?')}\n\n{content}\n")

        if not combined_content:
            raise ValueError("No valid carousel posts found")

        reel_content = "\n".join(combined_content)

        target_dir = self._get_target_dir(target_folder)

        reel_frontmatter = base_frontmatter.copy()
        reel_frontmatter["type"] = "reel"
        reel_frontmatter["status"] = "draft"
        reel_frontmatter["rev"] = "1.0"
        reel_frontmatter["created_at"] = datetime.now().isoformat()
        reel_frontmatter["updated_at"] = datetime.now().isoformat()

        reel_frontmatter["source_posts"] = carousel_posts
        reel_frontmatter["content_reuse_type"] = "carousel_to_reel"

        if reel_duration:
            reel_frontmatter["reel_duration"] = reel_duration

        reel_filename = "reel_from_carousel.md"
        reel_path = target_dir / reel_filename

        self._write_markdown_file(reel_path, reel_frontmatter, reel_content)

        return {
            "source_posts": carousel_posts,
            "target_folder": target_folder,
            "reel_path": str(reel_path.relative_to(self.storage.get_capability_root())),
            "reel_duration": reel_duration
        }

    def reel_to_stories(
        self,
        source_reel_path: str,
        target_folder: str,
        story_count: int = 3
    ) -> Dict[str, Any]:
        """
        Convert reel to multiple stories

        Args:
            source_reel_path: Path to source reel post (relative to workspace or Obsidian-style)
            target_folder: Target folder for story posts
            story_count: Number of stories to create (default: 3)

        Returns:
            Dictionary with created story posts information
        """
        full_source_path = self._resolve_post_path(source_reel_path)

        if not full_source_path.exists():
            raise FileNotFoundError(f"Source reel not found: {source_reel_path}")

        frontmatter, content = self._read_markdown_file(full_source_path)

        content_chunks = self._chunk_content(content, story_count)

        target_dir = self._get_target_dir(target_folder)

        created_stories = []

        for i, chunk in enumerate(content_chunks, 1):
            story_frontmatter = frontmatter.copy()
            story_frontmatter["type"] = "story"
            story_frontmatter["status"] = "draft"
            story_frontmatter["rev"] = "1.0"
            story_frontmatter["created_at"] = datetime.now().isoformat()
            story_frontmatter["updated_at"] = datetime.now().isoformat()

            story_frontmatter["story_number"] = i
            story_frontmatter["story_total"] = story_count
            story_frontmatter["source_post"] = source_reel_path
            story_frontmatter["content_reuse_type"] = "reel_to_stories"

            story_filename = f"story_{i:02d}.md"
            story_path = target_dir / story_filename

            self._write_markdown_file(story_path, story_frontmatter, chunk)

            created_stories.append({
                "story_number": i,
                "path": str(story_path.relative_to(self.storage.get_capability_root())),
                "content_preview": chunk[:100] + "..." if len(chunk) > 100 else chunk
            })

        return {
            "source_reel": source_reel_path,
            "target_folder": target_folder,
            "total_stories": story_count,
            "created_stories": created_stories
        }

    def _chunk_content(self, content: str, num_chunks: int) -> List[str]:
        """
        Chunk content into specified number of parts

        Args:
            content: Content to chunk
            num_chunks: Number of chunks to create

        Returns:
            List of content chunks
        """
        if num_chunks <= 0:
            raise ValueError("num_chunks must be greater than 0")

        content = content.strip()

        if not content:
            return [""] * num_chunks

        paragraphs = re.split(r'\n\n+', content)

        if len(paragraphs) <= num_chunks:
            chunks = paragraphs + [""] * (num_chunks - len(paragraphs))
            return chunks[:num_chunks]

        chunk_size = len(paragraphs) // num_chunks
        remainder = len(paragraphs) % num_chunks

        chunks = []
        start_idx = 0

        for i in range(num_chunks):
            end_idx = start_idx + chunk_size + (1 if i < remainder else 0)
            chunk_paragraphs = paragraphs[start_idx:end_idx]
            chunks.append("\n\n".join(chunk_paragraphs))
            start_idx = end_idx

        return chunks

    def _read_markdown_file(self, file_path: Path) -> tuple[Dict[str, Any], str]:
        """Read markdown file and parse frontmatter"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter_match = re.match(
                r"^---\n(.*?)\n---\n(.*)$",
                content,
                re.DOTALL
            )

            if frontmatter_match:
                frontmatter_str = frontmatter_match.group(1)
                body = frontmatter_match.group(2)
                frontmatter = yaml.safe_load(frontmatter_str) or {}
            else:
                frontmatter = {}
                body = content

            return frontmatter, body

        except Exception as e:
            logger.error(f"Failed to read markdown file {file_path}: {e}", exc_info=True)
            raise

    def _write_markdown_file(
        self,
        file_path: Path,
        frontmatter: Dict[str, Any],
        content: str
    ) -> None:
        """Write markdown file with frontmatter"""
        try:
            frontmatter_str = yaml.dump(
                frontmatter,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            )

            full_content = f"---\n{frontmatter_str}---\n{content}"

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(full_content)

        except Exception as e:
            logger.error(f"Failed to write markdown file {file_path}: {e}", exc_info=True)
            raise

