"""
Review System for IG Post

Manages review workflow including changelog tracking, review notes,
and decision logs for content revision cycles.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import yaml
import re

logger = logging.getLogger(__name__)


class ReviewSystem:
    """
    Manages review workflow for IG Posts

    Supports:
    - Changelog tracking
    - Review notes management
    - Decision log recording
    - Review status tracking
    """

    def __init__(self, vault_path: str):
        """
        Initialize Review System

        Args:
            vault_path: Path to Obsidian Vault
        """
        self.vault_path = Path(vault_path).expanduser().resolve()

    def add_changelog_entry(
        self,
        post_path: str,
        version: str,
        changes: str,
        author: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add changelog entry to post frontmatter

        Args:
            post_path: Path to post file (relative to vault)
            version: Version string (e.g., "1.1", "2.0")
            changes: Description of changes
            author: Author of changes (optional)

        Returns:
            Updated frontmatter with changelog entry
        """
        full_path = self.vault_path / post_path

        if not full_path.exists():
            raise FileNotFoundError(f"Post file not found: {post_path}")

        frontmatter, content = self._read_markdown_file(full_path)

        if "changelog" not in frontmatter:
            frontmatter["changelog"] = []

        changelog_entry = {
            "version": version,
            "changes": changes,
            "author": author,
            "timestamp": datetime.now().isoformat()
        }

        frontmatter["changelog"].append(changelog_entry)
        frontmatter["updated_at"] = datetime.now().isoformat()

        self._write_markdown_file(full_path, frontmatter, content)

        return frontmatter

    def add_review_note(
        self,
        post_path: str,
        reviewer: str,
        note: str,
        priority: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add review note to post frontmatter

        Args:
            post_path: Path to post file (relative to vault)
            reviewer: Reviewer name
            note: Review note content
            priority: Priority level (e.g., "high", "medium", "low")
            status: Review status (e.g., "pending", "addressed", "resolved")

        Returns:
            Updated frontmatter with review note
        """
        full_path = self.vault_path / post_path

        if not full_path.exists():
            raise FileNotFoundError(f"Post file not found: {post_path}")

        frontmatter, content = self._read_markdown_file(full_path)

        if "review_notes" not in frontmatter:
            frontmatter["review_notes"] = []

        review_note = {
            "reviewer": reviewer,
            "note": note,
            "priority": priority or "medium",
            "status": status or "pending",
            "timestamp": datetime.now().isoformat()
        }

        frontmatter["review_notes"].append(review_note)
        frontmatter["updated_at"] = datetime.now().isoformat()

        self._write_markdown_file(full_path, frontmatter, content)

        return frontmatter

    def add_decision_log(
        self,
        post_path: str,
        decision: str,
        rationale: Optional[str] = None,
        decision_maker: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add decision log entry to post frontmatter

        Args:
            post_path: Path to post file (relative to vault)
            decision: Decision description
            rationale: Rationale for decision (optional)
            decision_maker: Decision maker name (optional)

        Returns:
            Updated frontmatter with decision log entry
        """
        full_path = self.vault_path / post_path

        if not full_path.exists():
            raise FileNotFoundError(f"Post file not found: {post_path}")

        frontmatter, content = self._read_markdown_file(full_path)

        if "decision_log" not in frontmatter:
            frontmatter["decision_log"] = []

        decision_entry = {
            "decision": decision,
            "rationale": rationale,
            "decision_maker": decision_maker,
            "timestamp": datetime.now().isoformat()
        }

        frontmatter["decision_log"].append(decision_entry)
        frontmatter["updated_at"] = datetime.now().isoformat()

        self._write_markdown_file(full_path, frontmatter, content)

        return frontmatter

    def update_review_note_status(
        self,
        post_path: str,
        note_index: int,
        new_status: str
    ) -> Dict[str, Any]:
        """
        Update review note status

        Args:
            post_path: Path to post file (relative to vault)
            note_index: Index of review note in review_notes array
            new_status: New status (e.g., "addressed", "resolved", "rejected")

        Returns:
            Updated frontmatter
        """
        full_path = self.vault_path / post_path

        if not full_path.exists():
            raise FileNotFoundError(f"Post file not found: {post_path}")

        frontmatter, content = self._read_markdown_file(full_path)

        if "review_notes" not in frontmatter:
            raise ValueError("No review notes found in post")

        if note_index < 0 or note_index >= len(frontmatter["review_notes"]):
            raise ValueError(f"Invalid note index: {note_index}")

        frontmatter["review_notes"][note_index]["status"] = new_status
        frontmatter["review_notes"][note_index]["updated_at"] = datetime.now().isoformat()
        frontmatter["updated_at"] = datetime.now().isoformat()

        self._write_markdown_file(full_path, frontmatter, content)

        return frontmatter

    def get_review_summary(self, post_path: str) -> Dict[str, Any]:
        """
        Get review summary for a post

        Args:
            post_path: Path to post file (relative to vault)

        Returns:
            Review summary including changelog, review notes, and decision log
        """
        full_path = self.vault_path / post_path

        if not full_path.exists():
            raise FileNotFoundError(f"Post file not found: {post_path}")

        frontmatter, _ = self._read_markdown_file(full_path)

        changelog = frontmatter.get("changelog", [])
        review_notes = frontmatter.get("review_notes", [])
        decision_log = frontmatter.get("decision_log", [])

        pending_notes = [note for note in review_notes if note.get("status") == "pending"]
        high_priority_notes = [note for note in review_notes if note.get("priority") == "high"]

        summary = {
            "post_path": post_path,
            "changelog_count": len(changelog),
            "review_notes_count": len(review_notes),
            "pending_notes_count": len(pending_notes),
            "high_priority_notes_count": len(high_priority_notes),
            "decision_log_count": len(decision_log),
            "latest_changelog": changelog[-1] if changelog else None,
            "latest_review_note": review_notes[-1] if review_notes else None,
            "latest_decision": decision_log[-1] if decision_log else None,
            "review_status": "pending" if pending_notes else "resolved"
        }

        return summary

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

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(full_content)

        except Exception as e:
            logger.error(f"Failed to write markdown file {file_path}: {e}", exc_info=True)
            raise

