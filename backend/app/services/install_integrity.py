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
import shutil
from difflib import unified_diff
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

GENERATED_RUNTIME_ASSET_SIDECARS = {
    "ui_runtime_assets.json",
}

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
        cap_dir:  Installed capability root (e.g. ``capabilities/example_pack/``).
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


def _review_path(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError("dirty_review_path_outside_capability_root")
    return candidate


def _text_diff(current_path: Path, candidate_path: Path) -> List[str]:
    if not current_path.is_file() or not candidate_path.is_file():
        return []
    if current_path.stat().st_size > 262_144 or candidate_path.stat().st_size > 262_144:
        return []
    try:
        current = current_path.read_text(encoding="utf-8").splitlines()
        candidate = candidate_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    lines = unified_diff(
        current,
        candidate,
        fromfile="installed",
        tofile="candidate",
        lineterm="",
    )
    return [line[:500] for line in list(lines)[:120]]


def build_dirty_review_payload(
    installed_cap_dir: Path,
    candidate_cap_dir: Path,
    dirty: DirtyCheckResult,
) -> Dict[str, object]:
    """Compare every local change with the incoming candidate for review."""

    change_kinds = {
        **{path: "modified" for path in dirty.modified},
        **{path: "added" for path in dirty.added},
        **{path: "deleted" for path in dirty.deleted},
    }
    files = []
    for relative_path in sorted(change_kinds):
        installed_path = _review_path(installed_cap_dir, relative_path)
        candidate_path = _review_path(candidate_cap_dir, relative_path)
        installed_exists = installed_path.is_file()
        candidate_exists = candidate_path.is_file()
        installed_hash = _hash_file(installed_path) if installed_exists else None
        candidate_hash = _hash_file(candidate_path) if candidate_exists else None
        local_change_preserved = (
            installed_exists == candidate_exists
            and installed_hash == candidate_hash
        )
        files.append(
            {
                "path": relative_path,
                "local_change": change_kinds[relative_path],
                "installed_sha256": installed_hash,
                "candidate_sha256": candidate_hash,
                "candidate_state": (
                    "matches_local"
                    if local_change_preserved
                    else "differs_from_local"
                    if candidate_exists
                    else "absent"
                ),
                "local_change_preserved": local_change_preserved,
                "text_diff": _text_diff(installed_path, candidate_path),
            }
        )
    return {
        "schema_version": "mindscape.capability_install_dirty_review.v1",
        "file_count": len(files),
        "all_local_changes_preserved": all(
            bool(item["local_change_preserved"]) for item in files
        ),
        "files": files,
    }


def _load_installed_file_manifest(cap_dir: Path) -> Dict[str, str]:
    """Load the managed file list from ``.install_manifest.json``."""
    manifest_path = cap_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        return {}

    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            saved = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot load install manifest for stale-file pruning: %s", exc)
        return {}

    files = saved.get("files", {})
    return files if isinstance(files, dict) else {}


def _remove_empty_parents(path: Path, stop_at: Path) -> None:
    """Remove empty parent directories up to, but not including, ``stop_at``."""
    parent = path.parent
    stop_at = stop_at.resolve()
    while parent.exists() and parent.resolve() != stop_at:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def prune_stale_installed_files(
    installed_cap_dir: Path, incoming_cap_dir: Path
) -> List[str]:
    """
    Remove previously managed files that are absent from the incoming mindpack.

    Dirty-state detection protects local modifications before install starts. This
    pruning step handles the complementary case: a file was installed by an older
    pack version, then removed from cloud source, and should not remain in the
    local-core mirror after reinstall.
    """
    if not installed_cap_dir.exists() or not incoming_cap_dir.exists():
        return []

    installed_files = _load_installed_file_manifest(installed_cap_dir)
    if not installed_files:
        return []

    incoming_files = set(compute_dir_hashes(incoming_cap_dir).keys())
    pruned: List[str] = []

    for rel_path in sorted(installed_files):
        if rel_path in incoming_files:
            continue
        if rel_path in GENERATED_RUNTIME_ASSET_SIDECARS:
            continue

        target = installed_cap_dir / rel_path
        try:
            resolved_target = target.resolve()
            resolved_root = installed_cap_dir.resolve()
        except OSError:
            continue
        if resolved_root not in resolved_target.parents:
            logger.warning("Skipping stale-file prune outside capability root: %s", target)
            continue
        if not target.exists() and not target.is_symlink():
            continue

        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
        _remove_empty_parents(target, installed_cap_dir)
        pruned.append(rel_path)

    if pruned:
        logger.info(
            "Pruned %d stale managed file(s) from %s: %s",
            len(pruned),
            installed_cap_dir,
            ", ".join(pruned),
        )
    return pruned
