"""
Web Page Sandbox implementation

Manages dynamic web page projects with React components, page structure,
and deployment support.
"""

from typing import Optional, Dict, Any
import logging

from backend.app.services.sandbox.base_sandbox import BaseSandbox

logger = logging.getLogger(__name__)


class WebPageSandbox(BaseSandbox):
    """
    Sandbox for web page projects

    Manages:
    - Page structure (spec/, hero/, sections/, pages/)
    - React components
    - Deployment configuration
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
        self.sandbox_type = "web_page"

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

        return "; ".join(summary_parts) if summary_parts else "No changes"

    async def validate(self) -> Dict[str, Any]:
        """Validate web page sandbox structure"""
        errors = []
        warnings = []

        files = await self.list_files()
        file_paths = {f["path"] for f in files}

        required_dirs = ["spec", "hero", "sections", "pages"]
        for dir_name in required_dirs:
            has_files = any(f.startswith(f"{dir_name}/") for f in file_paths)
            if not has_files:
                warnings.append(f"Directory {dir_name}/ is empty")

        required_files = [
            "spec/site_structure.yaml",
            "spec/page.md",
        ]
        for req_file in required_files:
            if req_file not in file_paths:
                errors.append(f"Required file missing: {req_file}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

