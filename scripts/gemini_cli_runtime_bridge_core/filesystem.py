import os
from typing import Dict, List, Tuple

from .output import log


def _resolve_host_sandbox_path(sandbox_path: str, workspace_root: str) -> str:
    """Map container sandbox path (/app/...) to a host-accessible path."""
    if not sandbox_path:
        return ""
    if os.path.isdir(sandbox_path):
        return sandbox_path
    if not workspace_root or not sandbox_path.startswith("/app/"):
        return ""

    rel = sandbox_path[5:]
    candidate = os.path.join(workspace_root, rel)
    try:
        os.makedirs(candidate, exist_ok=True)
    except Exception as exc:
        log(f"Failed to create host sandbox {candidate}: {exc}")
        return ""
    return candidate if os.path.isdir(candidate) else ""


def _snapshot_files(root: str) -> Dict[str, Tuple[int, int]]:
    """Capture a lightweight recursive file snapshot for change detection."""
    if not root or not os.path.isdir(root):
        return {}

    snapshot: Dict[str, Tuple[int, int]] = {}
    skip_dirs = {".git", "__pycache__", "node_modules", ".pytest_cache"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in skip_dirs]
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            try:
                stat = os.stat(full_path)
            except OSError:
                continue
            rel_path = os.path.relpath(full_path, root)
            snapshot[rel_path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _diff_file_snapshots(
    before: Dict[str, Tuple[int, int]],
    after: Dict[str, Tuple[int, int]],
) -> Tuple[List[str], List[str]]:
    """Return created and modified relative paths between two snapshots."""
    created = sorted(path for path in after.keys() if path not in before)
    modified = sorted(
        path
        for path, after_meta in after.items()
        if path in before and before[path] != after_meta
    )
    return created, modified
