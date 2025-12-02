"""
Obsidian Tools Implementation

Tools for reading from and writing to Obsidian vaults.
Supports markdown parsing, frontmatter extraction, and bidirectional link handling.
"""
import os
import re
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import yaml

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema

logger = logging.getLogger(__name__)


def parse_frontmatter(content: str) -> tuple:
    """
    Parse YAML frontmatter from markdown content

    Returns:
        (frontmatter_dict, body_content)
    """
    frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(frontmatter_pattern, content, re.DOTALL)

    if match:
        frontmatter_str = match.group(1)
        body = match.group(2)
        try:
            frontmatter = yaml.safe_load(frontmatter_str) or {}
            return frontmatter, body
        except yaml.YAMLError:
            logger.warning("Failed to parse frontmatter YAML")
            return {}, content
    else:
        return {}, content


def extract_tags(content: str) -> List[str]:
    """Extract tags from markdown content (#tag format)"""
    tag_pattern = r'#([a-zA-Z0-9_-]+)'
    tags = re.findall(tag_pattern, content)
    return list(set(tags))


def extract_links(content: str) -> List[str]:
    """Extract Obsidian-style links [[note-title]]"""
    link_pattern = r'\[\[([^\]]+)\]\]'
    links = re.findall(link_pattern, content)
    return list(set(links))


class ObsidianListNotesTool(MindscapeTool):
    """List notes in Obsidian vault with optional filtering"""

    def __init__(self, vault_path: str, include_folders: Optional[List[str]] = None, exclude_folders: Optional[List[str]] = None):
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.include_folders = include_folders or []
        self.exclude_folders = exclude_folders or [".obsidian", "Templates"]

        if not self.vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        if not (self.vault_path / ".obsidian").exists():
            logger.warning(f"Path may not be an Obsidian vault (no .obsidian folder): {vault_path}")

        metadata = ToolMetadata(
            name="obsidian_list_notes",
            description=f"List notes in Obsidian vault at {self.vault_path}",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "folder": {
                        "type": "string",
                        "description": "Filter by folder path (relative to vault root)",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter by tag (e.g., 'research', 'paper')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of notes to return",
                        "default": 50
                    }
                },
                required=[]
            ),
            category="data",
            source_type="builtin",
            provider="obsidian",
            danger_level="low"
        )
        super().__init__(metadata)

    def _should_include_note(self, note_path: Path) -> bool:
        """Check if note should be included based on folder filters"""
        rel_path = note_path.relative_to(self.vault_path)
        path_parts = rel_path.parts

        for exclude in self.exclude_folders:
            if exclude in path_parts:
                return False

        if self.include_folders:
            for include in self.include_folders:
                if include in path_parts:
                    return True
            return False

        return True

    async def execute(
        self,
        folder: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """List notes in vault"""
        search_path = self.vault_path
        if folder:
            search_path = self.vault_path / folder
            if not search_path.exists():
                raise ValueError(f"Folder does not exist: {folder}")

        notes = []
        count = 0

        for md_file in search_path.rglob("*.md"):
            if count >= limit:
                break

            if not self._should_include_note(md_file):
                continue

            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()

                frontmatter, body = parse_frontmatter(content)
                tags = extract_tags(content)
                links = extract_links(content)

                if tag and tag not in tags:
                    continue

                rel_path = md_file.relative_to(self.vault_path)
                title = frontmatter.get("title") or md_file.stem

                preview = body[:200] if body else ""

                notes.append({
                    "path": str(rel_path).replace("\\", "/"),
                    "title": title,
                    "tags": tags,
                    "links": links,
                    "frontmatter": frontmatter,
                    "preview": preview,
                    "size": md_file.stat().st_size,
                    "modified": datetime.fromtimestamp(md_file.stat().st_mtime).isoformat()
                })
                count += 1
            except Exception as e:
                logger.warning(f"Error reading note {md_file}: {e}")
                continue

        return {
            "vault_path": str(self.vault_path),
            "notes": notes,
            "count": len(notes),
            "filters": {
                "folder": folder,
                "tag": tag
            }
        }


class ObsidianReadNoteTool(MindscapeTool):
    """Read a specific note from Obsidian vault"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).expanduser().resolve()

        if not self.vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        metadata = ToolMetadata(
            name="obsidian_read_note",
            description=f"Read note content from Obsidian vault at {self.vault_path}",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "note_path": {
                        "type": "string",
                        "description": "Relative path to note file (e.g., 'Research/paper.md')"
                    }
                },
                required=["note_path"]
            ),
            category="data",
            source_type="builtin",
            provider="obsidian",
            danger_level="low"
        )
        super().__init__(metadata)

    def _validate_path(self, note_path: str) -> Path:
        """Validate and resolve note path"""
        target = (self.vault_path / note_path).resolve()

        if not str(target).startswith(str(self.vault_path)):
            raise ValueError(f"Path traversal detected: {note_path}")

        if not target.exists():
            raise ValueError(f"Note does not exist: {note_path}")

        if not target.is_file():
            raise ValueError(f"Path is not a file: {note_path}")

        return target

    async def execute(self, note_path: str) -> Dict[str, Any]:
        """Read note content"""
        target_file = self._validate_path(note_path)

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter, body = parse_frontmatter(content)
            tags = extract_tags(content)
            links = extract_links(content)

            file_hash = hashlib.md5(content.encode()).hexdigest()

            return {
                "note_path": note_path,
                "title": frontmatter.get("title") or target_file.stem,
                "frontmatter": frontmatter,
                "body": body,
                "content": content,
                "tags": tags,
                "links": links,
                "size": target_file.stat().st_size,
                "hash": file_hash,
                "modified": datetime.fromtimestamp(target_file.stat().st_mtime).isoformat()
            }
        except Exception as e:
            raise ValueError(f"Error reading note: {str(e)}")


class ObsidianWriteNoteTool(MindscapeTool):
    """Write or overwrite a note in Obsidian vault"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).expanduser().resolve()

        if not self.vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        metadata = ToolMetadata(
            name="obsidian_write_note",
            description=f"Write or overwrite note in Obsidian vault at {self.vault_path}",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "note_path": {
                        "type": "string",
                        "description": "Relative path to note file (e.g., 'Research/paper.md')"
                    },
                    "title": {
                        "type": "string",
                        "description": "Note title (will be added to frontmatter)"
                    },
                    "body": {
                        "type": "string",
                        "description": "Note content in markdown format"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to add (e.g., ['research', 'paper'])"
                    },
                    "frontmatter": {
                        "type": "object",
                        "description": "Additional frontmatter fields"
                    }
                },
                required=["note_path", "body"]
            ),
            category="content",
            source_type="builtin",
            provider="obsidian",
            danger_level="medium"
        )
        super().__init__(metadata)

    def _validate_path(self, note_path: str) -> Path:
        """Validate and resolve note path"""
        target = (self.vault_path / note_path).resolve()

        if not str(target).startswith(str(self.vault_path)):
            raise ValueError(f"Path traversal detected: {note_path}")

        if ".obsidian" in note_path:
            raise ValueError("Cannot write to .obsidian folder")

        return target

    async def execute(
        self,
        note_path: str,
        body: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        frontmatter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Write note to vault"""
        target_file = self._validate_path(note_path)

        target_file.parent.mkdir(parents=True, exist_ok=True)

        frontmatter_dict = frontmatter or {}
        if title:
            frontmatter_dict["title"] = title
        if tags:
            frontmatter_dict["tags"] = tags
        frontmatter_dict["created"] = datetime.now().isoformat()
        frontmatter_dict["updated"] = datetime.now().isoformat()

        frontmatter_yaml = yaml.dump(frontmatter_dict, allow_unicode=True, default_flow_style=False)
        content = f"---\n{frontmatter_yaml}---\n\n{body}"

        try:
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "note_path": note_path,
                "title": title or target_file.stem,
                "size": len(content),
                "success": True,
                "created": not target_file.exists() if target_file.exists() else False
            }
        except Exception as e:
            raise ValueError(f"Error writing note: {str(e)}")


class ObsidianAppendNoteTool(MindscapeTool):
    """Append content to existing note in Obsidian vault"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).expanduser().resolve()

        if not self.vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")

        metadata = ToolMetadata(
            name="obsidian_append_note",
            description=f"Append content to note in Obsidian vault at {self.vault_path}",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "note_path": {
                        "type": "string",
                        "description": "Relative path to note file"
                    },
                    "body": {
                        "type": "string",
                        "description": "Content to append (markdown format)"
                    },
                    "section_title": {
                        "type": "string",
                        "description": "Optional section title (e.g., '2025-11-27 Generated by Mindscape')"
                    }
                },
                required=["note_path", "body"]
            ),
            category="content",
            source_type="builtin",
            provider="obsidian",
            danger_level="medium"
        )
        super().__init__(metadata)

    def _validate_path(self, note_path: str) -> Path:
        """Validate and resolve note path"""
        target = (self.vault_path / note_path).resolve()

        if not str(target).startswith(str(self.vault_path)):
            raise ValueError(f"Path traversal detected: {note_path}")

        return target

    async def execute(
        self,
        note_path: str,
        body: str,
        section_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Append content to note"""
        target_file = self._validate_path(note_path)

        if not target_file.exists():
            raise ValueError(f"Note does not exist: {note_path}. Use obsidian_write_note to create new notes.")

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                existing_content = f.read()

            frontmatter, existing_body = parse_frontmatter(existing_content)

            timestamp = datetime.now().strftime("%Y-%m-%d")
            section_header = f"\n\n## {section_title or f'{timestamp} Generated by Mindscape'}\n\n"
            new_body = existing_body + section_header + body

            frontmatter["updated"] = datetime.now().isoformat()
            frontmatter_yaml = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)
            new_content = f"---\n{frontmatter_yaml}---\n\n{new_body}"

            with open(target_file, "w", encoding="utf-8") as f:
                f.write(new_content)

            return {
                "note_path": note_path,
                "section_title": section_title,
                "appended_size": len(body),
                "success": True
            }
        except Exception as e:
            raise ValueError(f"Error appending to note: {str(e)}")




