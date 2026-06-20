"""Path filters for workspace sandbox synchronization."""

import fnmatch
import os
from pathlib import Path
from typing import Iterator, List, Optional, Tuple


PROTECTED_PATTERNS = [
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "node_modules/",
    ".git/",
    ".gitignore",
    ".env",
    ".env.*",
    "tsconfig.json",
    "next.config.*",
    "vite.config.*",
    "tailwind.config.*",
    "postcss.config.*",
    ".next/",
    "dist/",
    "build/",
    "out/",
    "__pycache__/",
    "*.pyc",
    ".DS_Store",
]


DEFAULT_SYNC_DIRECTORIES = {
    "web_page": ["spec", "hero", "sections", "pages", "components", "styles", "public"],
    "threejs_hero": ["components", "scenes", "assets"],
    "writing_project": ["chapters", "drafts", "notes", "outline"],
    "project_repo": None,
}


def get_sync_directories(sandbox_type: str) -> Optional[List[str]]:
    """Get sync directories for a sandbox type."""
    return DEFAULT_SYNC_DIRECTORIES.get(sandbox_type)


def is_protected(file_path: str) -> bool:
    """Check if file matches protected patterns."""
    for pattern in PROTECTED_PATTERNS:
        if fnmatch.fnmatch(file_path, pattern) or pattern in file_path:
            return True
    return False


def should_sync_file(file_path: str, sync_dirs: Optional[List[str]]) -> bool:
    """Check if a file should be synced."""
    if is_protected(file_path):
        return False

    if sync_dirs is None:
        return True

    for dir_name in sync_dirs:
        if file_path.startswith(dir_name + "/") or file_path.startswith(
            dir_name + "\\"
        ):
            return True
        if file_path == dir_name or file_path.startswith(dir_name):
            return True

    return False


def iter_workspace_files(
    workspace_path: Path,
    sync_dirs: Optional[List[str]],
) -> Iterator[Tuple[Path, str]]:
    """Yield workspace files that pass sync filters."""
    if sync_dirs:
        for dir_name in sync_dirs:
            source_dir = workspace_path / dir_name
            if not source_dir.exists():
                continue

            for root, _, files in os.walk(source_dir):
                for filename in files:
                    source_file = Path(root) / filename
                    relative_path = str(source_file.relative_to(workspace_path))
                    if should_sync_file(relative_path, sync_dirs):
                        yield source_file, relative_path
        return

    if not workspace_path.exists():
        return

    for root, _, files in os.walk(workspace_path):
        for filename in files:
            source_file = Path(root) / filename
            relative_path = str(source_file.relative_to(workspace_path))
            if should_sync_file(relative_path, None):
                yield source_file, relative_path


def collect_workspace_paths(
    workspace_path: Path,
    sync_dirs: Optional[List[str]],
) -> set[str]:
    """Collect workspace paths that pass sync filters."""
    return {relative_path for _, relative_path in iter_workspace_files(workspace_path, sync_dirs)}
