"""
Project Repo Sandbox implementation

Manages code projects with patch and merge mechanisms, supporting Git integration.
"""

from typing import Optional, Dict, Any
import logging

from backend.app.services.sandbox.base_sandbox import BaseSandbox

logger = logging.getLogger(__name__)


class ProjectRepoSandbox(BaseSandbox):
    """
    Sandbox for code projects

    Manages:
    - Code files and project structure
    - Patch collections (patches/)
    - Git branch management (branch/)
    - Merge mechanisms
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
        self.sandbox_type = "project_repo"

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

        code_changes = []
        code_extensions = [".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs"]
        for path in modified:
            if any(path.endswith(ext) for ext in code_extensions):
                code_changes.append(path)

        if code_changes:
            summary_parts.append(f"Updated code files: {len(code_changes)}")

        return "; ".join(summary_parts) if summary_parts else "No changes"

    async def validate(self) -> Dict[str, Any]:
        """Validate project repo sandbox structure"""
        errors = []
        warnings = []

        files = await self.list_files()
        file_paths = {f["path"] for f in files}

        has_patches = any(f.startswith("patches/") for f in file_paths)
        has_branch = any(f.startswith("branch/") for f in file_paths)
        has_sandbox = any(f.startswith("sandbox/") for f in file_paths)

        if not (has_patches or has_branch or has_sandbox):
            warnings.append("No patches/, branch/, or sandbox/ directory found")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

