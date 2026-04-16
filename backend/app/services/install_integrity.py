"""
Install Integrity

File-hash-based dirty-state detection for capability packs.

Records SHA-256 hashes of all installed files after each install.
Before overwriting, compares current file state against the recorded
hashes to detect local modifications.
"""

import difflib
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = ".install_manifest.json"

# Directories/files to skip when hashing
_SKIP_PATTERNS = {"__pycache__", ".pyc", ".pyo", ".DS_Store"}
_DIFF_REVIEW_MAX_ITEMS = 12
_DIFF_PREVIEW_CONTEXT_LINES = 3
_DIFF_PREVIEW_MAX_LINES = 80


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


def _safe_hash_file(file_path: Path) -> Optional[str]:
    try:
        if not file_path.is_file():
            return None
        return _hash_file(file_path)
    except OSError as exc:
        logger.warning("Failed to hash %s for diff review: %s", file_path, exc)
        return None


def _read_text_lines_for_diff(file_path: Path) -> tuple[Optional[List[str]], Optional[str]]:
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        return None, f"Unable to read file: {exc}"

    if b"\x00" in raw:
        return None, "Binary file; diff preview omitted."

    return raw.decode("utf-8", errors="replace").splitlines(keepends=True), None


def _build_unified_diff_preview(
    *,
    local_path: Path,
    incoming_path: Path,
    relative_path: str,
) -> tuple[Optional[str], bool, Optional[str]]:
    local_lines, local_note = _read_text_lines_for_diff(local_path)
    incoming_lines, incoming_note = _read_text_lines_for_diff(incoming_path)

    note_parts = [note for note in (local_note, incoming_note) if note]
    if local_lines is None or incoming_lines is None:
        note = "; ".join(note_parts) if note_parts else None
        return None, False, note

    diff_lines = list(
        difflib.unified_diff(
            local_lines,
            incoming_lines,
            fromfile=f"local-core/{relative_path}",
            tofile=f"incoming-pack/{relative_path}",
            n=_DIFF_PREVIEW_CONTEXT_LINES,
        )
    )
    if not diff_lines:
        return None, False, None

    truncated = len(diff_lines) > _DIFF_PREVIEW_MAX_LINES
    preview = "".join(diff_lines[:_DIFF_PREVIEW_MAX_LINES])
    if truncated:
        preview += (
            f"\n... ({len(diff_lines) - _DIFF_PREVIEW_MAX_LINES} more diff lines omitted)\n"
        )
    return preview, truncated, None


def _build_review_item(
    *,
    change_type: str,
    relative_path: str,
    existing_cap_dir: Path,
    incoming_cap_dir: Path,
) -> Dict[str, Any]:
    local_path = existing_cap_dir / relative_path
    incoming_path = incoming_cap_dir / relative_path
    local_exists = local_path.is_file()
    incoming_exists = incoming_path.is_file()
    local_hash = _safe_hash_file(local_path)
    incoming_hash = _safe_hash_file(incoming_path)
    incoming_matches_local = (
        bool(local_hash)
        and bool(incoming_hash)
        and str(local_hash) == str(incoming_hash)
    )

    preview = None
    preview_truncated = False
    note: Optional[str] = None

    if local_exists and incoming_exists and not incoming_matches_local:
        preview, preview_truncated, note = _build_unified_diff_preview(
            local_path=local_path,
            incoming_path=incoming_path,
            relative_path=relative_path,
        )
        comparison_state = "differs_from_incoming"
        if note is None:
            note = (
                "Incoming pack differs from the current local-core file. "
                "Review whether local fixes are already upstreamed before overwrite."
            )
    elif incoming_matches_local:
        comparison_state = "matches_incoming"
        note = "Incoming pack already matches the current local-core file."
    elif local_exists and not incoming_exists:
        comparison_state = "local_only"
        note = (
            "Path exists only in local-core. Incoming pack does not contain it. "
            "Review whether this local change is missing from cloud source."
        )
    elif not local_exists and incoming_exists:
        comparison_state = "incoming_only"
        note = (
            "Path is currently missing in local-core. Incoming pack contains it "
            "and will restore it if overwrite proceeds."
        )
    else:
        comparison_state = "absent_both"
        note = (
            "Path is absent in both local-core and incoming pack. "
            "Review manifest drift before overwrite."
        )

    return {
        "path": relative_path,
        "change_type": change_type,
        "comparison_state": comparison_state,
        "incoming_matches_local": incoming_matches_local if (local_exists and incoming_exists) else None,
        "local_exists": local_exists,
        "incoming_exists": incoming_exists,
        "local_hash": local_hash,
        "incoming_hash": incoming_hash,
        "preview": preview,
        "preview_truncated": preview_truncated,
        "note": note,
    }


def build_dirty_review_payload(
    existing_cap_dir: Path,
    incoming_cap_dir: Path,
    dirty: "DirtyCheckResult",
) -> Dict[str, Any]:
    """
    Build per-file review guidance for dirty-state overwrite conflicts.

    Compares the current local-core capability files against the incoming pack
    so installers can inspect whether local modifications are already present in
    cloud source before forcing an overwrite.
    """
    ordered_paths = (
        [("modified", path) for path in dirty.modified]
        + [("added", path) for path in dirty.added]
        + [("deleted", path) for path in dirty.deleted]
    )
    previewed = ordered_paths[:_DIFF_REVIEW_MAX_ITEMS]
    items = [
        _build_review_item(
            change_type=change_type,
            relative_path=relative_path,
            existing_cap_dir=existing_cap_dir,
            incoming_cap_dir=incoming_cap_dir,
        )
        for change_type, relative_path in previewed
    ]
    return {
        "items": items,
        "total_items": len(ordered_paths),
        "previewed_items": len(items),
        "truncated_items": max(0, len(ordered_paths) - len(items)),
        "matching_items": sum(
            1 for item in items if item.get("comparison_state") == "matches_incoming"
        ),
        "conflicting_items": sum(
            1 for item in items if item.get("comparison_state") != "matches_incoming"
        ),
    }


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
