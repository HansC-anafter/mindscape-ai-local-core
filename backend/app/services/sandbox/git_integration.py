"""
Git integration for Sandbox system

Provides Git operations for sandbox projects with user confirmation.
"""

import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class SandboxGitIntegration:
    """
    Git integration for sandbox projects

    Provides Git operations with safety checks and user confirmation.
    """

    @staticmethod
    async def get_branches(repo_path: str) -> List[str]:
        """
        Get list of Git branches

        Args:
            repo_path: Path to Git repository

        Returns:
            List of branch names
        """
        try:
            result = subprocess.run(
                ["git", "branch", "-a"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                branches = [
                    line.strip().replace("*", "").strip()
                    for line in result.stdout.split("\n")
                    if line.strip() and not line.strip().startswith("remotes/origin/HEAD")
                ]
                return [b.replace("remotes/origin/", "") for b in branches if b]
            return []
        except Exception as e:
            logger.error(f"Failed to get branches: {e}")
            return []

    @staticmethod
    async def get_current_branch(repo_path: str) -> Optional[str]:
        """
        Get current Git branch

        Args:
            repo_path: Path to Git repository

        Returns:
            Current branch name or None
        """
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"Failed to get current branch: {e}")
            return None

    @staticmethod
    async def create_branch(repo_path: str, branch_name: str) -> bool:
        """
        Create a new Git branch

        Args:
            repo_path: Path to Git repository
            branch_name: Branch name to create

        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to create branch: {e}")
            return False

    @staticmethod
    async def switch_branch(repo_path: str, branch_name: str) -> bool:
        """
        Switch to a Git branch

        Args:
            repo_path: Path to Git repository
            branch_name: Branch name to switch to

        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "checkout", branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to switch branch: {e}")
            return False

    @staticmethod
    async def commit_changes(
        repo_path: str,
        commit_message: str,
        files: Optional[List[str]] = None
    ) -> bool:
        """
        Commit changes to Git repository

        Args:
            repo_path: Path to Git repository
            commit_message: Commit message
            files: Optional list of specific files to commit (all if None)

        Returns:
            True if successful, False otherwise
        """
        try:
            if files:
                for file_path in files:
                    subprocess.run(
                        ["git", "add", file_path],
                        cwd=repo_path,
                        capture_output=True,
                        timeout=10
                    )
            else:
                subprocess.run(
                    ["git", "add", "."],
                    cwd=repo_path,
                    capture_output=True,
                    timeout=10
                )

            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to commit changes: {e}")
            return False

    @staticmethod
    async def push_branch(
        repo_path: str,
        branch_name: str,
        remote: str = "origin"
    ) -> bool:
        """
        Push branch to remote repository

        Args:
            repo_path: Path to Git repository
            branch_name: Branch name to push
            remote: Remote name (default: origin)

        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "push", remote, branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to push branch: {e}")
            return False

    @staticmethod
    async def get_status(repo_path: str) -> Dict[str, Any]:
        """
        Get Git repository status

        Args:
            repo_path: Path to Git repository

        Returns:
            Dictionary with status information
        """
        try:
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )

            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )

            return {
                "has_changes": bool(status_result.stdout.strip()),
                "current_branch": branch_result.stdout.strip() if branch_result.returncode == 0 else None,
                "status_output": status_result.stdout.strip(),
            }
        except Exception as e:
            logger.error(f"Failed to get Git status: {e}")
            return {
                "has_changes": False,
                "current_branch": None,
                "status_output": "",
            }

