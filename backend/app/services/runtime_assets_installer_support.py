import base64
import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path

SCRIPT_DIR_EXCLUDES = {
    "__pycache__",
    ".git",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}
SCRIPT_FILE_EXCLUDES = {".DS_Store"}
SCRIPT_SUFFIX_EXCLUDES = {".pyc", ".pyo"}
RUNTIME_NAMESPACE_DIRS = {
    "analysis",
    "core",
    "generation",
    "repositories",
}
RUNTIME_MIRROR_DIRS = {
    *RUNTIME_NAMESPACE_DIRS,
    "api",
    "docs",
    "evals",
    "jobs",
    "migrations",
    "models",
    "routes",
    "schema",
    "scripts",
    "services",
    "tools",
    "workflows",
}


def _clear_directory_contents(target_dir: Path) -> None:
    """Remove all children from an existing directory without deleting the root."""
    if not target_dir.exists():
        return

    for child in target_dir.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
        else:
            shutil.rmtree(child)


def _safe_asset_segment(value: object, fallback: str) -> str:
    raw = str(value or fallback).strip() or fallback
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in raw)
    return safe.strip(".-") or fallback


def _sha256_integrity(file_path: Path) -> str:
    digest = hashlib.sha256(file_path.read_bytes()).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def _should_skip_runtime_mirror_asset(relative_path: Path) -> bool:
    if any(part in SCRIPT_DIR_EXCLUDES for part in relative_path.parts):
        return True
    if relative_path.name in SCRIPT_FILE_EXCLUDES:
        return True
    return relative_path.suffix in SCRIPT_SUFFIX_EXCLUDES


def _iter_runtime_mirror_files(root: Path):
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(root)
        if _should_skip_runtime_mirror_asset(relative_path):
            continue
        yield relative_path, file_path


def _build_staging_root(capability_code: str) -> Path:
    """Build a staging path outside watched application source trees."""
    configured_root = os.environ.get("MINDSCAPE_CAPABILITY_INSTALL_STAGING_ROOT")
    base_dir = (
        Path(configured_root)
        if configured_root
        else Path(tempfile.gettempdir()) / "mindscape-capability-install-staging"
    )
    return base_dir / f"{capability_code}-{uuid.uuid4().hex}"
