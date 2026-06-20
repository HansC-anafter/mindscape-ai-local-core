"""File operations for workspace sandbox synchronization."""

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from .filters import collect_workspace_paths, iter_workspace_files, should_sync_file

logger = logging.getLogger(__name__)


async def sync_workspace_files_to_sandbox(
    workspace_path: Path,
    sandbox,
    sync_dirs: Optional[List[str]],
) -> List[str]:
    """Copy workspace files into a sandbox."""
    synced_files = []

    for source_file, relative_path in iter_workspace_files(workspace_path, sync_dirs):
        try:
            content = source_file.read_text(encoding="utf-8")
            await sandbox.write_file(relative_path, content)
            synced_files.append(relative_path)
            logger.debug(f"Synced: {relative_path}")
        except Exception as exc:
            logger.warning(f"Failed to sync {relative_path}: {exc}")

    if sandbox.sandbox_type == "web_page":
        if hasattr(sandbox, "sync_pages_to_app"):
            await sandbox.sync_pages_to_app()

    return synced_files


async def sync_sandbox_files_to_workspace(
    workspace_path: Path,
    sandbox,
    sync_dirs: Optional[List[str]],
    create_backup: bool = True,
) -> Dict[str, Any]:
    """Copy sandbox files back into the workspace."""
    synced_files = []
    backed_up_files = []
    workspace_path.mkdir(parents=True, exist_ok=True)

    sandbox_files = await sandbox.list_files()

    for file_info in sandbox_files:
        file_path = file_info["path"]

        if not should_sync_file(file_path, sync_dirs):
            logger.debug(f"Skipping file (not in sync dirs or protected): {file_path}")
            continue

        try:
            content = await sandbox.read_file(file_path)
            target_path = workspace_path / file_path

            if create_backup and target_path.exists():
                backup_path = target_path.with_suffix(target_path.suffix + ".backup")
                shutil.copy2(target_path, backup_path)
                backed_up_files.append(str(file_path))
                logger.debug(f"Backed up: {file_path}")

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            synced_files.append(file_path)
            logger.debug(f"Synced to workspace: {file_path}")

        except Exception as exc:
            logger.warning(f"Failed to sync {file_path} to workspace: {exc}")

    return {
        "synced_files": synced_files,
        "backed_up_files": backed_up_files,
        "status": "success",
    }


async def get_workspace_sandbox_diff(
    workspace_path: Path,
    sandbox,
    sync_dirs: Optional[List[str]],
) -> Dict[str, Any]:
    """Build a diff between workspace files and sandbox files."""
    sandbox_files = await sandbox.list_files()
    sandbox_paths = {
        file_info["path"]
        for file_info in sandbox_files
        if should_sync_file(file_info["path"], sync_dirs)
    }

    workspace_paths = collect_workspace_paths(workspace_path, sync_dirs)

    added = sandbox_paths - workspace_paths
    deleted = workspace_paths - sandbox_paths
    common = sandbox_paths & workspace_paths

    modified = []
    for path in common:
        try:
            sandbox_content = await sandbox.read_file(path)
            workspace_content = (workspace_path / path).read_text(encoding="utf-8")
            if sandbox_content != workspace_content:
                modified.append(path)
        except Exception:
            pass

    return {
        "added": list(added),
        "modified": modified,
        "deleted": list(deleted),
        "unchanged": list(common - set(modified)),
        "sandbox_type": sandbox.sandbox_type,
        "sync_directories": sync_dirs,
    }
