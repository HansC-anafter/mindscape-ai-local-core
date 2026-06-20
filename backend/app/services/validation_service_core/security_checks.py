"""Security checks for validation service."""

from pathlib import Path
from typing import Dict, List, Tuple


def validate_security(cap_dir: Path, result: Dict) -> None:
    """Run security checks."""
    path_ok, path_errors = check_path_traversal(cap_dir)
    result["validation_stages"]["path_traversal"] = {
        "ok": path_ok,
        "errors": path_errors,
    }
    result["errors"].extend(path_errors)

    perm_ok, perm_warnings = check_file_permissions(cap_dir)
    result["validation_stages"]["permissions"] = {
        "ok": perm_ok,
        "warnings": perm_warnings,
    }
    result["warnings"].extend(perm_warnings)


def check_path_traversal(cap_dir: Path) -> Tuple[bool, List[str]]:
    """Check for path traversal attacks."""
    errors = []

    for item in cap_dir.rglob("*"):
        rel_path = item.relative_to(cap_dir)
        path_str = str(rel_path)

        if ".." in path_str:
            errors.append(f"Path traversal detected: {path_str}")

        if path_str.startswith("/"):
            errors.append(f"Absolute path detected: {path_str}")

    return len(errors) == 0, errors


def check_file_permissions(cap_dir: Path) -> Tuple[bool, List[str]]:
    """Check file permissions."""
    warnings = []

    for item in cap_dir.rglob("*"):
        if item.is_file():
            if item.stat().st_mode & 0o111 and not item.suffix == ".py":
                warnings.append(f"Unexpected executable file: {item}")

    return True, warnings
