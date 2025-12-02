"""
Obsidian Vault Scanner Service

Scans Obsidian vaults for note changes and generates events for embedding.
Only processes research-related notes based on folder/tag filters.
"""
import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ObsidianScanner:
    """
    Scanner for Obsidian vaults

    Features:
    - Detects new/updated notes
    - Filters by folder/tag criteria
    - Hash-based change detection
    - Emits events for embedding pipeline
    """

    def __init__(
        self,
        vault_path: str,
        include_folders: Optional[List[str]] = None,
        exclude_folders: Optional[List[str]] = None,
        include_tags: Optional[List[str]] = None
    ):
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.include_folders = include_folders or []
        self.exclude_folders = exclude_folders or [".obsidian", "Templates"]
        self.include_tags = include_tags or ["research", "paper", "project"]
        self._note_hashes: Dict[str, str] = {}
        self._load_hash_cache()

    def _load_hash_cache(self):
        """Load hash cache from disk (optional, for persistence)"""
        cache_file = self.vault_path / ".mindscape_hashes.json"
        if cache_file.exists():
            try:
                import json
                with open(cache_file, "r") as f:
                    self._note_hashes = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load hash cache: {e}")

    def _save_hash_cache(self):
        """Save hash cache to disk"""
        cache_file = self.vault_path / ".mindscape_hashes.json"
        try:
            import json
            with open(cache_file, "w") as f:
                json.dump(self._note_hashes, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save hash cache: {e}")

    def _should_process_note(self, note_path: Path, tags: List[str]) -> bool:
        """Check if note should be processed for embedding"""
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

        if self.include_tags:
            for tag in self.include_tags:
                if tag in tags:
                    return True
            return False

        return True

    def scan_vault(self) -> List[Dict[str, Any]]:
        """
        Scan vault for changed notes

        Returns:
            List of note change events
        """
        from backend.app.services.tools.obsidian.obsidian_tools import parse_frontmatter, extract_tags

        events = []

        for md_file in self.vault_path.rglob("*.md"):
            if ".obsidian" in md_file.parts:
                continue

            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    content = f.read()

                _, body = parse_frontmatter(content)
                tags = extract_tags(content)

                if not self._should_process_note(md_file, tags):
                    continue

                content_hash = hashlib.md5(content.encode()).hexdigest()
                rel_path = str(md_file.relative_to(self.vault_path)).replace("\\", "/")

                previous_hash = self._note_hashes.get(rel_path)

                if previous_hash != content_hash:
                    frontmatter, body = parse_frontmatter(content)
                    title = frontmatter.get("title") or md_file.stem

                    should_embed = True
                    if self.include_folders:
                        path_parts = rel_path.parts
                        should_embed = any(include in path_parts for include in self.include_folders)
                    if self.include_tags and should_embed:
                        should_embed = any(tag in tags for tag in self.include_tags)

                    event = {
                        "event_type": "OBSIDIAN_NOTE_UPDATED",
                        "note_path": rel_path,
                        "vault_path": str(self.vault_path),
                        "title": title,
                        "content": body,
                        "hash": content_hash,
                        "tags": tags,
                        "size": md_file.stat().st_size,
                        "modified": datetime.fromtimestamp(md_file.stat().st_mtime).isoformat(),
                        "is_new": previous_hash is None,
                        "should_embed": should_embed
                    }
                    events.append(event)
                    self._note_hashes[rel_path] = content_hash

            except Exception as e:
                logger.warning(f"Error scanning note {md_file}: {e}")
                continue

        if events:
            self._save_hash_cache()

        return events

    def get_note_for_embedding(self, note_path: str) -> Optional[Dict[str, Any]]:
        """
        Get note content for embedding

        Returns:
            Note content with metadata, or None if note should not be embedded
        """
        from backend.app.services.tools.obsidian.obsidian_tools import parse_frontmatter, extract_tags

        target_file = self.vault_path / note_path

        if not target_file.exists():
            return None

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter, body = parse_frontmatter(content)
            tags = extract_tags(content)

            if not self._should_process_note(target_file, tags):
                return None

            return {
                "note_path": note_path,
                "title": frontmatter.get("title") or target_file.stem,
                "content": body,
                "tags": tags,
                "frontmatter": frontmatter
            }
        except Exception as e:
            logger.error(f"Error reading note for embedding: {e}")
            return None




