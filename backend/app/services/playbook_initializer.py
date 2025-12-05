"""
PlaybookInitializer - implements Claude-style initializer agent pattern

Creates initial artifacts and setup for playbook executions, following
Claude's pattern of establishing context before main execution begins.
"""

import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class PlaybookInitializer:
    """
    Initializes playbook executions following Claude's initializer agent pattern

    On first execution of a playbook, creates essential artifacts:
    - playbook_feature_list.json: Feature inventory
    - playbook_progress.log: Progress tracking
    - init.sh: Environment setup script (if needed)
    - Initial git commit (if applicable)
    """

    def __init__(self, workspace_root: str):
        """
        Initialize playbook initializer

        Args:
            workspace_root: Root directory for workspace artifacts
        """
        self.workspace_root = Path(workspace_root)

    async def initialize_playbook_execution(
        self,
        execution_id: str,
        playbook_code: str,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        Initialize a playbook execution

        Creates initial artifacts and establishes execution context.
        This follows Claude's pattern of "get bearings" before starting work.

        Args:
            execution_id: Unique execution identifier
            playbook_code: Playbook code identifier
            workspace_id: Workspace identifier

        Returns:
            Initialization results with artifact paths
        """
        # Create execution directory
        execution_dir = self.workspace_root / "executions" / execution_id
        execution_dir.mkdir(parents=True, exist_ok=True)

        artifacts = {}

        try:
            # Create feature list
            feature_list_path = execution_dir / "playbook_feature_list.json"
            feature_list = await self._create_feature_list(playbook_code, execution_id)
            await self._write_json_file(feature_list_path, feature_list)
            artifacts["feature_list"] = str(feature_list_path)

            # Create progress log
            progress_log_path = execution_dir / "playbook_progress.log"
            initial_log = await self._create_initial_progress_log(playbook_code, execution_id)
            await self._write_text_file(progress_log_path, initial_log)
            artifacts["progress_log"] = str(progress_log_path)

            # Create init script if needed
            init_script_path = execution_dir / "init.sh"
            init_script = await self._create_init_script(playbook_code, execution_id)
            if init_script:
                await self._write_text_file(init_script_path, init_script)
                artifacts["init_script"] = str(init_script_path)

            # Create initial git commit if in git repository
            git_commit = await self._create_initial_git_commit(execution_dir, execution_id)
            if git_commit:
                artifacts["initial_commit"] = git_commit

            logger.info(f"Initialized playbook execution: {execution_id} with artifacts: {list(artifacts.keys())}")

            return {
                "success": True,
                "execution_id": execution_id,
                "artifacts": artifacts,
                "workspace": str(execution_dir),
                "initialized_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to initialize playbook execution {execution_id}: {e}")
            return {
                "success": False,
                "execution_id": execution_id,
                "error": str(e),
                "initialized_at": datetime.utcnow().isoformat()
            }

    async def get_bearings(self, execution_id: str) -> Dict[str, Any]:
        """
        Get bearings for resuming an execution

        Reads existing artifacts to understand current state and determine
        next steps. This is the "get bearings" phase that Claude uses.

        Args:
            execution_id: Execution identifier

        Returns:
            Current execution context and next steps
        """
        execution_dir = self.workspace_root / "executions" / execution_id

        if not execution_dir.exists():
            return {
                "status": "not_initialized",
                "execution_id": execution_id,
                "next_action": "initialize"
            }

        context = {
            "execution_id": execution_id,
            "workspace": str(execution_dir),
            "artifacts": {},
            "status": "initialized"
        }

        # Read feature list
        feature_list_path = execution_dir / "playbook_feature_list.json"
        if feature_list_path.exists():
            try:
                feature_list = await self._read_json_file(feature_list_path)
                context["artifacts"]["feature_list"] = feature_list
            except Exception as e:
                logger.warning(f"Failed to read feature list for {execution_id}: {e}")

        # Read progress log
        progress_log_path = execution_dir / "playbook_progress.log"
        if progress_log_path.exists():
            try:
                progress_log = await self._read_text_file(progress_log_path)
                context["artifacts"]["progress_log"] = progress_log
                context["last_progress"] = await self._parse_last_progress(progress_log)
            except Exception as e:
                logger.warning(f"Failed to read progress log for {execution_id}: {e}")

        # Determine next action based on progress
        context["next_action"] = await self._determine_next_action(context)

        logger.info(f"Got bearings for execution: {execution_id}, next action: {context['next_action']}")
        return context

    async def _create_feature_list(self, playbook_code: str, execution_id: str) -> Dict[str, Any]:
        """
        Create initial feature list for playbook

        Args:
            playbook_code: Playbook identifier
            execution_id: Execution identifier

        Returns:
            Feature list data structure
        """
        # This would typically analyze the playbook definition
        # For now, create a basic structure
        return {
            "playbook_code": playbook_code,
            "execution_id": execution_id,
            "features": [
                {
                    "id": "core_functionality",
                    "name": "Core Functionality",
                    "description": "Implement the main features of the playbook",
                    "status": "pending",
                    "estimated_complexity": "medium"
                },
                {
                    "id": "error_handling",
                    "name": "Error Handling",
                    "description": "Add robust error handling and recovery",
                    "status": "pending",
                    "estimated_complexity": "low"
                },
                {
                    "id": "testing",
                    "name": "Testing",
                    "description": "Create comprehensive tests",
                    "status": "pending",
                    "estimated_complexity": "medium"
                }
            ],
            "created_at": datetime.utcnow().isoformat(),
            "version": "1.0"
        }

    async def _create_initial_progress_log(self, playbook_code: str, execution_id: str) -> str:
        """
        Create initial progress log for playbook execution tracking.

        Generates a structured log file that tracks execution progress with
        initial status information for monitoring and debugging purposes.

        Args:
            playbook_code: Playbook identifier
            execution_id: Execution identifier

        Returns:
            Initial progress log content as formatted string
        """
        timestamp = datetime.utcnow().isoformat()
        return f"""# Playbook Execution Progress Log
# Playbook: {playbook_code}
# Execution: {execution_id}
# Started: {timestamp}

{timestamp} - INFO: Playbook execution initialized
{timestamp} - INFO: Created feature list and progress tracking
{timestamp} - STATUS: ready_to_start
"""

    async def _create_init_script(self, playbook_code: str, execution_id: str) -> Optional[str]:
        """
        Create initialization script if needed

        Args:
            playbook_code: Playbook identifier
            execution_id: Execution identifier

        Returns:
            Init script content or None
        """
        # Only create init script for certain playbook types
        if playbook_code.startswith("infrastructure_") or playbook_code.startswith("deployment_"):
            return f"""#!/bin/bash
# Initialization script for {playbook_code}
# Execution: {execution_id}

echo "Initializing environment for {playbook_code}..."

# Add environment-specific setup here
# export NODE_ENV=production
# npm install
# etc.

echo "Environment initialized successfully"
"""
        return None

    async def _create_initial_git_commit(self, execution_dir: Path, execution_id: str) -> Optional[str]:
        """
        Create initial git commit if in a git repository

        Args:
            execution_dir: Execution directory
            execution_id: Execution identifier

        Returns:
            Commit hash or None
        """
        try:
            # Check if we're in a git repository
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=execution_dir,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # We're in a git repo, create initial commit
                subprocess.run(["git", "add", "."], cwd=execution_dir, check=True)
                result = subprocess.run(
                    ["git", "commit", "-m", f"Initial commit for playbook execution {execution_id}"],
                    cwd=execution_dir,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    # Get commit hash
                    hash_result = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=execution_dir,
                        capture_output=True,
                        text=True
                    )
                    if hash_result.returncode == 0:
                        commit_hash = hash_result.stdout.strip()
                        logger.info(f"Created initial git commit: {commit_hash}")
                        return commit_hash

        except Exception as e:
            logger.debug(f"Git operations not available or failed: {e}")

        return None

    async def _determine_next_action(self, context: Dict[str, Any]) -> str:
        """
        Determine next action based on current context

        Args:
            context: Current execution context

        Returns:
            Next action identifier
        """
        progress_log = context.get("artifacts", {}).get("progress_log", "")
        last_progress = context.get("last_progress", {})

        # Simple logic based on progress log
        if "completed" in progress_log.lower():
            return "execution_complete"
        elif "error" in progress_log.lower():
            return "handle_error"
        elif "ready_to_start" in progress_log.lower():
            return "begin_execution"
        else:
            return "continue_execution"

    async def _parse_last_progress(self, progress_log: str) -> Dict[str, Any]:
        """
        Parse last progress entry from log

        Args:
            progress_log: Progress log content

        Returns:
            Last progress information
        """
        lines = progress_log.strip().split('\n')
        # Simple parsing - take the last non-comment line
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith('#'):
                return {"last_entry": line}
        return {}

    async def _write_json_file(self, path: Path, data: Dict[str, Any]) -> None:
        """Write data to JSON file"""
        import json
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def _write_text_file(self, path: Path, content: str) -> None:
        """Write content to text file"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    async def _read_json_file(self, path: Path) -> Dict[str, Any]:
        """Read data from JSON file"""
        import json
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async def _read_text_file(self, path: Path) -> str:
        """Read content from text file"""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
