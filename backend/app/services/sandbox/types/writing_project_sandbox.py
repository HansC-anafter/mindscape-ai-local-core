"""
Writing Project Sandbox implementation

Manages writing projects with structured chapters and outline.
"""

from typing import Optional, Dict, Any
import logging

from backend.app.services.sandbox.base_sandbox import BaseSandbox

logger = logging.getLogger(__name__)


class WritingProjectSandbox(BaseSandbox):
    """
    Sandbox for writing projects

    Manages:
    - Project outline (outline.md)
    - Chapter files (ch01.md, ch02.md, ...)
    - Metadata (meta.json)
    - Pure text content processing
    """

    def __init__(
        self,
        sandbox_id: str,
        sandbox_type: str,
        workspace_id: str,
        storage,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(sandbox_id, sandbox_type, workspace_id, storage, metadata)
        self.sandbox_type = "writing_project"

    async def get_change_summary(
        self,
        from_version: Optional[str],
        to_version: Optional[str]
    ) -> str:
        """Get AI-generated summary of changes between versions"""
        from_files = await self.list_files(version=from_version)
        to_files = await self.list_files(version=to_version)

        from_paths = {f["path"] for f in from_files}
        to_paths = {f["path"] for f in to_files}

        added = to_paths - from_paths
        removed = from_paths - to_paths
        modified = from_paths & to_paths

        summary_parts = []
        if added:
            summary_parts.append(f"Added {len(added)} file(s)")
        if removed:
            summary_parts.append(f"Removed {len(removed)} file(s)")
        if modified:
            summary_parts.append(f"Modified {len(modified)} file(s)")

        chapter_changes = []
        for path in modified:
            if path.startswith("ch") and path.endswith(".md"):
                chapter_changes.append(path)

        if chapter_changes:
            summary_parts.append(f"Updated chapters: {', '.join(chapter_changes)}")

        return "; ".join(summary_parts) if summary_parts else "No changes"

    async def validate(self) -> Dict[str, Any]:
        """Validate writing project sandbox structure"""
        errors = []
        warnings = []

        files = await self.list_files()
        file_paths = {f["path"] for f in files}

        required_files = [
            "outline.md",
        ]
        for req_file in required_files:
            if req_file not in file_paths:
                errors.append(f"Required file missing: {req_file}")

        has_chapters = any(f.startswith("ch") and f.endswith(".md") for f in file_paths)
        if not has_chapters:
            warnings.append("No chapter files found")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

