"""
Deployment service for sandbox projects

Handles file copying, Git command generation, and deployment instructions.
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from backend.app.services.sandbox.sandbox_manager import SandboxManager
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class DeploymentService:
    """
    Service for deploying sandbox projects to target directories

    Handles:
    - File copying from sandbox to target path
    - Git command generation (does not execute)
    - VM deployment instruction generation
    """

    def __init__(self, store: MindscapeStore):
        """
        Initialize deployment service

        Args:
            store: MindscapeStore instance
        """
        self.store = store
        self.sandbox_manager = SandboxManager(store)

    async def deploy_sandbox(
        self,
        workspace_id: str,
        sandbox_id: str,
        target_path: str,
        files: Optional[List[str]] = None,
        git_branch: Optional[str] = None,
        commit_message: Optional[str] = None,
        auto_commit: bool = False,
        auto_push: bool = False
    ) -> Dict[str, Any]:
        """
        Deploy sandbox files to target path

        Args:
            workspace_id: Workspace identifier
            sandbox_id: Sandbox identifier
            target_path: Target directory path
            files: Optional list of specific files to deploy (all files if None)
            git_branch: Optional Git branch name
            commit_message: Optional commit message
            auto_commit: Whether to automatically commit (default: False)
            auto_push: Whether to automatically push (default: False)

        Returns:
            Dictionary with deployment results:
            - status: "success" or "error"
            - files_copied: List of copied file paths
            - git_commands: Generated Git commands (not executed)
            - vm_commands: VM deployment commands
        """
        try:
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
            if not sandbox:
                raise ValueError(f"Sandbox {sandbox_id} not found")

            target = Path(target_path)
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)

            files_to_copy = files or []
            if not files_to_copy:
                all_files = await sandbox.list_files()
                files_to_copy = [f["path"] for f in all_files]

            files_copied = []
            for file_path in files_to_copy:
                try:
                    content = await sandbox.read_file(file_path)
                    target_file = target / file_path

                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(target_file, "w", encoding="utf-8") as f:
                        f.write(content)

                    files_copied.append(str(target_file))
                except Exception as e:
                    logger.error(f"Failed to copy file {file_path}: {e}")

            git_commands = self._generate_git_commands(
                target_path=target_path,
                files_copied=files_copied,
                branch=git_branch,
                commit_message=commit_message,
                auto_commit=auto_commit,
                auto_push=auto_push
            )

            vm_commands = self._generate_vm_commands(target_path)

            return {
                "status": "success",
                "files_copied": files_copied,
                "git_commands": git_commands,
                "vm_commands": vm_commands,
            }
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return {
                "status": "error",
                "error": str(e),
            }

    def _generate_git_commands(
        self,
        target_path: str,
        files_copied: List[str],
        branch: Optional[str] = None,
        commit_message: Optional[str] = None,
        auto_commit: bool = False,
        auto_push: bool = False
    ) -> Dict[str, Any]:
        """
        Generate Git commands (not executed)

        Args:
            target_path: Target directory path
            files_copied: List of copied file paths
            branch: Optional branch name
            commit_message: Optional commit message
            auto_commit: Whether commit command should be executed
            auto_push: Whether push command should be executed

        Returns:
            Dictionary with Git command information
        """
        commands = []
        relative_files = [os.path.relpath(f, target_path) for f in files_copied]

        if branch:
            commands.append(f"git checkout -b {branch}")

        commands.append("git add " + " ".join(relative_files))

        if commit_message:
            commands.append(f"git commit -m '{commit_message}'")
        else:
            commands.append("git commit -m 'Deploy sandbox files'")

        if branch and auto_push:
            commands.append(f"git push origin {branch}")

        return {
            "executed": auto_commit,
            "commands": commands,
            "branch": branch,
            "commit_message": commit_message,
        }

    def _generate_vm_commands(self, target_path: str) -> List[str]:
        """
        Generate VM deployment commands

        Args:
            target_path: Target directory path

        Returns:
            List of VM deployment commands
        """
        return [
            f"cd {target_path}",
            "git pull origin main",
            "npm install",
            "npm run build",
            "pm2 restart site-brand",
        ]

