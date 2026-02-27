"""
Install Integrity

File-hash-based dirty-state detection for capability packs.

Records SHA-256 hashes of all installed files after each install.
Before overwriting, compares current file state against the recorded
hashes to detect local modifications.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = ".install_manifest.json"

# Directories/files to skip when hashing
_SKIP_PATTERNS = {"__pycache__", ".pyc", ".pyo", ".DS_Store"}


@dataclass
class DirtyCheckResult:
    """Result of a dirty-state check."""

    is_dirty: bool = False
    modified: List[str] = field(default_factory=list)
    added: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    installed_version: Optional[str] = None
    installed_at: Optional[str] = None

    def summary(self) -> str:
        """Human-readable summary of changes."""
        parts = []
        if self.modified:
            parts.append(f"Modified ({len(self.modified)}): {', '.join(self.modified)}")
        if self.added:
            parts.append(f"Added ({len(self.added)}): {', '.join(self.added)}")
        if self.deleted:
            parts.append(f"Deleted ({len(self.deleted)}): {', '.join(self.deleted)}")
        if not parts:
            return "No local modifications detected."
        return "; ".join(parts)


def _should_skip(path: Path) -> bool:
    """Check if a file/directory should be excluded from hashing."""
    for part in path.parts:
        if part in _SKIP_PATTERNS:
            return True
    if path.suffix in {".pyc", ".pyo"}:
        return True
    return False


def _hash_file(file_path: Path) -> str:
    """Compute SHA-256 hash of a single file."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def compute_dir_hashes(dir_path: Path) -> Dict[str, str]:
    """
    Compute SHA-256 of every file in *dir_path* (recursively).

    Args:
        dir_path: Root directory to scan.

    Returns:
        Dict mapping relative file path -> ``sha256:<hex>`` string.
        Excludes ``__pycache__``, ``.pyc`` etc.
    """
    hashes: Dict[str, str] = {}
    if not dir_path.exists():
        return hashes

    for file_path in sorted(dir_path.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(dir_path)
        if _should_skip(rel):
            continue
        # Skip the manifest itself to avoid circular reference
        if rel.name == MANIFEST_FILENAME:
            continue
        try:
            hashes[str(rel)] = _hash_file(file_path)
        except OSError as exc:
            logger.warning("Failed to hash %s: %s", file_path, exc)

    return hashes


def save_install_manifest(
    cap_dir: Path,
    version: str,
    hashes: Dict[str, str],
) -> Path:
    """
    Write ``.install_manifest.json`` to the capability directory.

    Args:
        cap_dir:  Installed capability root (e.g. ``capabilities/yogacoach/``).
        version:  Manifest ``version`` field value.
        hashes:   Output of :func:`compute_dir_hashes`.

    Returns:
        Path to the written manifest file.
    """
    manifest_path = cap_dir / MANIFEST_FILENAME
    data = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "file_count": len(hashes),
        "files": hashes,
    }
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    logger.info(
        "Saved install manifest for v%s (%d files) at %s",
        version,
        len(hashes),
        manifest_path,
    )
    return manifest_path


def check_dirty_state(cap_dir: Path) -> DirtyCheckResult:
    """
    Compare current files against the recorded ``.install_manifest.json``.

    Args:
        cap_dir: Installed capability root directory.

    Returns:
        :class:`DirtyCheckResult` with lists of modified/added/deleted files.
        If no ``.install_manifest.json`` exists, returns ``is_dirty=False``
        (first install, nothing to protect).
    """
    manifest_path = cap_dir / MANIFEST_FILENAME
    result = DirtyCheckResult()

    if not manifest_path.exists():
        # First install — no previous state to protect
        return result

    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            saved = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        # Fail-closed: manifest exists but is unreadable → treat as dirty
        # to prevent silent overwrite of potentially modified files.
        logger.warning("Install manifest is corrupt or unreadable: %s", exc)
        result.is_dirty = True
        result.modified = ["<manifest unreadable — cannot determine changes>"]
        result.installed_version = "<unknown>"
        return result

    result.installed_version = saved.get("version")
    result.installed_at = saved.get("installed_at")
    saved_files: Dict[str, str] = saved.get("files", {})

    # Compute current state
    current_files = compute_dir_hashes(cap_dir)

    # Compare
    all_keys = set(saved_files.keys()) | set(current_files.keys())
    for key in sorted(all_keys):
        in_saved = key in saved_files
        in_current = key in current_files

        if in_saved and in_current:
            if saved_files[key] != current_files[key]:
                result.modified.append(key)
        elif in_saved and not in_current:
            result.deleted.append(key)
        elif not in_saved and in_current:
            result.added.append(key)

    result.is_dirty = bool(result.modified or result.added or result.deleted)
    return result
