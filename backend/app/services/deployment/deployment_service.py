"""
Deployment service for sandbox projects

Handles file copying, Git command generation, and deployment instructions.
Supports Git operations execution with user confirmation.
Tracks deployment history integrated with version management.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import json

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

            git_results = {}
            if auto_commit:
                git_results = await self._execute_git_commands(
                    target_path=target_path,
                    git_commands=git_commands,
                    auto_push=auto_push
                )

            deployment_record = await self._record_deployment(
                workspace_id=workspace_id,
                sandbox_id=sandbox_id,
                target_path=target_path,
                files_copied=files_copied,
                git_commands=git_commands,
                git_results=git_results
            )

            vm_commands = self._generate_vm_commands(target_path)

            return {
                "status": "success",
                "files_copied": files_copied,
                "git_commands": git_commands,
                "git_results": git_results if auto_commit else {},
                "vm_commands": vm_commands,
                "deployment_id": deployment_record.get("deployment_id"),
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

    async def _execute_git_commands(
        self,
        target_path: str,
        git_commands: Dict[str, Any],
        auto_push: bool = False
    ) -> Dict[str, Any]:
        """
        Execute Git commands with user confirmation

        Args:
            target_path: Target directory path
            git_commands: Git commands dictionary from _generate_git_commands
            auto_push: Whether to push after commit

        Returns:
            Dictionary with execution results
        """
        results = {
            "executed": [],
            "errors": [],
            "branch_created": False,
            "committed": False,
            "pushed": False,
        }

        try:
            target = Path(target_path)
            if not target.exists():
                raise ValueError(f"Target path does not exist: {target_path}")

            commands = git_commands.get("commands", [])
            branch = git_commands.get("branch")

            for cmd in commands:
                try:
                    if cmd.startswith("git checkout -b"):
                        result = subprocess.run(
                            cmd,
                            shell=True,
                            cwd=target,
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        if result.returncode == 0:
                            results["branch_created"] = True
                            results["executed"].append(cmd)
                        else:
                            results["errors"].append(f"{cmd}: {result.stderr}")
                    elif cmd.startswith("git add"):
                        result = subprocess.run(
                            cmd,
                            shell=True,
                            cwd=target,
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        if result.returncode == 0:
                            results["executed"].append(cmd)
                        else:
                            results["errors"].append(f"{cmd}: {result.stderr}")
                    elif cmd.startswith("git commit"):
                        result = subprocess.run(
                            cmd,
                            shell=True,
                            cwd=target,
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        if result.returncode == 0:
                            results["committed"] = True
                            results["executed"].append(cmd)
                        else:
                            results["errors"].append(f"{cmd}: {result.stderr}")
                    elif cmd.startswith("git push") and auto_push:
                        result = subprocess.run(
                            cmd,
                            shell=True,
                            cwd=target,
                            capture_output=True,
                            text=True,
                            timeout=60
                        )
                        if result.returncode == 0:
                            results["pushed"] = True
                            results["executed"].append(cmd)
                        else:
                            results["errors"].append(f"{cmd}: {result.stderr}")
                except subprocess.TimeoutExpired:
                    results["errors"].append(f"{cmd}: Timeout")
                except Exception as e:
                    results["errors"].append(f"{cmd}: {str(e)}")

        except Exception as e:
            logger.error(f"Failed to execute Git commands: {e}")
            results["errors"].append(str(e))

        return results

    async def _record_deployment(
        self,
        workspace_id: str,
        sandbox_id: str,
        target_path: str,
        files_copied: List[str],
        git_commands: Dict[str, Any],
        git_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Record deployment history

        Args:
            workspace_id: Workspace identifier
            sandbox_id: Sandbox identifier
            target_path: Target deployment path
            files_copied: List of copied files
            git_commands: Git commands dictionary
            git_results: Git execution results

        Returns:
            Deployment record dictionary
        """
        try:
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
            if not sandbox:
                return {}

            deployment_id = f"deploy-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            deployment_record = {
                "deployment_id": deployment_id,
                "sandbox_id": sandbox_id,
                "workspace_id": workspace_id,
                "target_path": target_path,
                "timestamp": datetime.now().isoformat(),
                "files_copied": files_copied,
                "git_branch": git_commands.get("branch"),
                "commit_message": git_commands.get("commit_message"),
                "git_executed": git_commands.get("executed", False),
                "git_results": git_results,
            }

            sandbox_path = self.sandbox_manager._get_sandbox_path(
                sandbox_id,
                workspace_id,
                sandbox.sandbox_type
            )

            deployments_path = sandbox_path / "deployments.json"
            deployments = []

            if deployments_path.exists():
                try:
                    with open(deployments_path, "r", encoding="utf-8") as f:
                        deployments = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to read deployment history: {e}")

            deployments.append(deployment_record)

            with open(deployments_path, "w", encoding="utf-8") as f:
                json.dump(deployments[-50:], f, indent=2)

            return deployment_record

        except Exception as e:
            logger.error(f"Failed to record deployment: {e}")
            return {}

    async def get_deployment_history(
        self,
        workspace_id: str,
        sandbox_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get deployment history for a sandbox

        Args:
            workspace_id: Workspace identifier
            sandbox_id: Sandbox identifier
            limit: Maximum number of records to return

        Returns:
            List of deployment records
        """
        try:
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
            if not sandbox:
                return []

            sandbox_path = self.sandbox_manager._get_sandbox_path(
                sandbox_id,
                workspace_id,
                sandbox.sandbox_type
            )

            deployments_path = sandbox_path / "deployments.json"
            if not deployments_path.exists():
                return []

            with open(deployments_path, "r", encoding="utf-8") as f:
                deployments = json.load(f)

            return deployments[-limit:]

        except Exception as e:
            logger.error(f"Failed to get deployment history: {e}")
            return []

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

