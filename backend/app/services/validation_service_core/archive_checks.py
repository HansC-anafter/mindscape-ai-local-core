"""Mindpack archive checks for validation service."""

import tarfile
from pathlib import Path
from typing import List, Tuple


def validate_mindpack_file(mindpack_path: Path) -> Tuple[bool, List[str]]:
    """Validate .mindpack file format."""
    errors = []

    if not mindpack_path.exists():
        return False, [f"Mindpack file not found: {mindpack_path}"]

    if not mindpack_path.suffix == ".mindpack":
        errors.append(
            f"Invalid file extension: expected .mindpack, got {mindpack_path.suffix}"
        )

    file_size = mindpack_path.stat().st_size
    if file_size == 0:
        errors.append("Mindpack file is empty")
    elif file_size > 100 * 1024 * 1024:
        errors.append(
            f"Mindpack file too large: {file_size / (1024*1024):.1f}MB"
        )

    try:
        with tarfile.open(mindpack_path, "r:gz") as tar:
            members = tar.getmembers()
            if not members:
                errors.append("Mindpack file is empty (no files inside)")

            for member in members:
                if ".." in member.name or member.name.startswith("/"):
                    errors.append(f"Unsafe path in mindpack: {member.name}")
    except tarfile.TarError as exc:
        errors.append(f"Invalid tar.gz format: {exc}")
    except Exception as exc:
        errors.append(f"Failed to open mindpack file: {exc}")

    return len(errors) == 0, errors


def validate_extracted_structure(extracted_dir: Path) -> Tuple[bool, List[str]]:
    """Validate extracted directory structure."""
    errors = []

    dirs = [entry for entry in extracted_dir.iterdir() if entry.is_dir()]
    if len(dirs) != 1:
        errors.append(f"Expected exactly one capability directory, found {len(dirs)}")
        return False, errors

    cap_dir = dirs[0]
    manifest_path = cap_dir / "manifest.yaml"
    if not manifest_path.exists():
        errors.append("manifest.yaml not found in extracted directory")

    return len(errors) == 0, errors
