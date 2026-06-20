"""Manifest checks for validation service."""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def validate_manifest(
    local_core_root: Path,
    manifest: Dict,
    manifest_path: Path,
    cap_dir: Path,
    result: Dict,
) -> None:
    """Run manifest validation stages."""
    schema_ok, schema_errors = validate_manifest_schema(manifest)
    result["validation_stages"]["manifest_schema"] = {
        "ok": schema_ok,
        "errors": schema_errors,
    }
    result["errors"].extend(schema_errors)

    files_ok, files_errors, files_warnings = validate_manifest_files(manifest, cap_dir)
    result["validation_stages"]["manifest_files"] = {
        "ok": files_ok,
        "errors": files_errors,
        "warnings": files_warnings,
    }
    result["errors"].extend(files_errors)
    result["warnings"].extend(files_warnings)

    script_ok, script_errors, script_warnings = validate_manifest_with_script(
        local_core_root, manifest_path, cap_dir
    )
    result["validation_stages"]["manifest_script"] = {
        "ok": script_ok,
        "errors": script_errors,
        "warnings": script_warnings,
    }
    result["errors"].extend(script_errors)
    result["warnings"].extend(script_warnings)


def validate_manifest_schema(manifest: Dict) -> Tuple[bool, List[str]]:
    """Validate manifest schema."""
    errors = []

    required_fields = ["code", "version", "portability"]
    for field in required_fields:
        if field not in manifest:
            errors.append(f"Missing required field: {field}")

    if "code" in manifest and not isinstance(manifest["code"], str):
        errors.append("Field 'code' must be a string")

    if "version" in manifest:
        version_str = manifest["version"]
        if not isinstance(version_str, str):
            errors.append("Field 'version' must be a string")
        elif not re.match(r"^\d+\.\d+\.\d+", version_str):
            errors.append(f"Invalid version format: {version_str} (expected semver)")

    playbooks = manifest.get("playbooks", [])
    if not isinstance(playbooks, list):
        errors.append("Field 'playbooks' must be a list")
    else:
        for index, playbook in enumerate(playbooks):
            if not isinstance(playbook, dict):
                errors.append(f"Playbook {index} must be a dictionary")
            elif "code" not in playbook:
                errors.append(f"Playbook {index} missing 'code' field")

    return len(errors) == 0, errors


def validate_manifest_files(
    manifest: Dict,
    cap_dir: Path,
) -> Tuple[bool, List[str], List[str]]:
    """Validate manifest file existence."""
    errors = []
    warnings = []

    playbooks = manifest.get("playbooks", [])
    for playbook in playbooks:
        playbook_code = playbook.get("code")
        spec_path = playbook.get("spec_path")
        if spec_path:
            spec_file = cap_dir / spec_path
            if not spec_file.exists():
                errors.append(
                    f"Playbook {playbook_code}: spec file not found: {spec_path}"
                )
            else:
                try:
                    with open(spec_file, "r") as file_obj:
                        json.load(file_obj)
                except json.JSONDecodeError as exc:
                    errors.append(
                        f"Playbook {playbook_code}: invalid JSON in spec file: {exc}"
                    )

        locales = playbook.get("locales", [])
        path_template = playbook.get("path", "playbooks/{locale}/{code}.md")
        for locale in locales:
            locale_path = cap_dir / path_template.format(
                locale=locale,
                code=playbook_code,
            )
            if not locale_path.exists():
                errors.append(
                    f"Playbook {playbook_code} ({locale}): locale file not found: "
                    f"{locale_path}"
                )

    return len(errors) == 0, errors, warnings


def validate_manifest_with_script(
    local_core_root: Path,
    manifest_path: Path,
    cap_dir: Path,
) -> Tuple[bool, List[str], List[str]]:
    """Validate manifest using the local-core manifest validator."""
    errors = []
    warnings = []

    validate_script = local_core_root / "scripts" / "ci" / "validate_manifest.py"
    if not validate_script.exists():
        warnings.append("validate_manifest.py not found, skipping advanced validation")
        return True, [], warnings

    try:
        result = subprocess.run(
            [sys.executable, str(validate_script), str(cap_dir)],
            cwd=str(local_core_root),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            for line in result.stdout.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                lowered = stripped.lower()
                if "error" in lowered or "failed" in lowered:
                    errors.append(stripped)
                elif "warning" in lowered:
                    warnings.append(stripped)

            if result.stderr:
                errors.append(result.stderr.strip())
    except subprocess.TimeoutExpired:
        errors.append("Validation script timed out")
    except Exception as exc:
        errors.append(f"Validation script execution failed: {exc}")

    return len(errors) == 0, errors, warnings
