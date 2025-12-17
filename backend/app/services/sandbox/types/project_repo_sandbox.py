"""
Project Repo Sandbox implementation

Manages code projects with patch and merge mechanisms, supporting Git integration.
"""

from typing import Optional, Dict, Any, List
import logging
from pathlib import Path

from backend.app.services.sandbox.base_sandbox import BaseSandbox
from backend.app.services.sandbox.git_integration import SandboxGitIntegration

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
        """
        Get AI-generated summary of changes between versions

        Uses LLM to generate a natural language summary of changes.

        Args:
            from_version: Source version identifier
            to_version: Target version identifier

        Returns:
            AI-generated summary string
        """
        from_files = await self.list_files(version=from_version)
        to_files = await self.list_files(version=to_version)

        from_paths = {f["path"] for f in from_files}
        to_paths = {f["path"] for f in to_files}

        added = to_paths - from_paths
        removed = from_paths - to_paths
        modified = from_paths & to_paths

        changes = []
        for path in added:
            changes.append(f"Added: {path}")
        for path in removed:
            changes.append(f"Removed: {path}")
        for path in modified:
            try:
                from_content = await self.read_file(path, version=from_version)
                to_content = await self.read_file(path, version=to_version)
                if from_content != to_content:
                    changes.append(f"Modified: {path}")
            except Exception as e:
                logger.warning(f"Failed to compare file {path}: {e}")
                changes.append(f"Modified: {path}")

        if not changes:
            return "No changes detected"

        changes_text = "\n".join(changes[:50])

        try:
            from backend.app.services.playbook_runner import PlaybookRunner
            from backend.app.services.mindscape_store import MindscapeStore

            store = getattr(self.storage, 'store', None)
            if store and isinstance(store, MindscapeStore):
                runner = PlaybookRunner(store)
                profile_id = store.get_default_profile_id()
                if profile_id:
                    llm_manager = runner.llm_provider_manager.get_llm_manager(profile_id)
                    if llm_manager:
                        prompt = f"""Generate a concise summary of the following code changes:

{changes_text}

Provide a brief, natural language summary of what changed in this version update."""

                        response = await llm_manager.generate_text(prompt, max_tokens=200)
                        if response and hasattr(response, 'text'):
                            return response.text.strip()
                        elif isinstance(response, str):
                            return response.strip()
            return "; ".join(changes[:5])
        except Exception as e:
            logger.warning(f"Failed to generate AI summary, using fallback: {e}")
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

    async def get_git_branches(self) -> List[str]:
        """
        Get list of Git branches for this sandbox

        Returns:
            List of branch names
        """
        sandbox_path = self.storage.base_path / self.sandbox_id / "current"
        if sandbox_path.exists():
            return await SandboxGitIntegration.get_branches(str(sandbox_path))
        return []

    async def get_current_git_branch(self) -> Optional[str]:
        """
        Get current Git branch for this sandbox

        Returns:
            Current branch name or None
        """
        sandbox_path = self.storage.base_path / self.sandbox_id / "current"
        if sandbox_path.exists():
            return await SandboxGitIntegration.get_current_branch(str(sandbox_path))
        return None

    async def create_git_branch(self, branch_name: str) -> bool:
        """
        Create a new Git branch

        Args:
            branch_name: Branch name to create

        Returns:
            True if successful, False otherwise
        """
        sandbox_path = self.storage.base_path / self.sandbox_id / "current"
        if sandbox_path.exists():
            return await SandboxGitIntegration.create_branch(str(sandbox_path), branch_name)
        return False

    async def switch_git_branch(self, branch_name: str) -> bool:
        """
        Switch to a Git branch

        Args:
            branch_name: Branch name to switch to

        Returns:
            True if successful, False otherwise
        """
        sandbox_path = self.storage.base_path / self.sandbox_id / "current"
        if sandbox_path.exists():
            return await SandboxGitIntegration.switch_branch(str(sandbox_path), branch_name)
        return False

    async def commit_git_changes(
        self,
        commit_message: str,
        files: Optional[List[str]] = None
    ) -> bool:
        """
        Commit changes to Git repository

        Args:
            commit_message: Commit message
            files: Optional list of specific files to commit

        Returns:
            True if successful, False otherwise
        """
        sandbox_path = self.storage.base_path / self.sandbox_id / "current"
        if sandbox_path.exists():
            return await SandboxGitIntegration.commit_changes(
                str(sandbox_path),
                commit_message,
                files
            )
        return False

    async def push_git_branch(
        self,
        branch_name: str,
        remote: str = "origin"
    ) -> bool:
        """
        Push branch to remote repository

        Args:
            branch_name: Branch name to push
            remote: Remote name (default: origin)

        Returns:
            True if successful, False otherwise
        """
        sandbox_path = self.storage.base_path / self.sandbox_id / "current"
        if sandbox_path.exists():
            return await SandboxGitIntegration.push_branch(
                str(sandbox_path),
                branch_name,
                remote
            )
        return False

    async def get_git_status(self) -> Dict[str, Any]:
        """
        Get Git repository status

        Returns:
            Dictionary with status information
        """
        sandbox_path = self.storage.base_path / self.sandbox_id / "current"
        if sandbox_path.exists():
            return await SandboxGitIntegration.get_status(str(sandbox_path))
        return {
            "has_changes": False,
            "current_branch": None,
            "status_output": "",
        }

