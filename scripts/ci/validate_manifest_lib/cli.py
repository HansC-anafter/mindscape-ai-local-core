import argparse
import json
import sys
from pathlib import Path
from typing import List

from .manifest_validator import validate_manifest
from .models import ValidationResult


def validate_directory(directory: Path) -> List[ValidationResult]:
    """
    Validate manifests for all capabilities in directory.

    Args:
        directory: Directory path

    Returns:
        All validation results
    """
    results = []

    # If directory itself contains manifest.yaml
    manifest_path = directory / "manifest.yaml"
    if manifest_path.exists():
        results.append(validate_manifest(manifest_path))
        return results

    # Otherwise iterate subdirectories
    for cap_dir in directory.iterdir():
        if not cap_dir.is_dir():
            continue
        if cap_dir.name.startswith("_") or cap_dir.name.startswith("."):
            continue

        manifest_path = cap_dir / "manifest.yaml"
        if manifest_path.exists():
            results.append(validate_manifest(manifest_path))

    return results


def format_results(results: List[ValidationResult], verbose: bool = False) -> str:
    """Format validation results."""
    lines = []

    total_errors = sum(len(r.errors) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    valid_count = sum(1 for r in results if r.valid)

    lines.append(f"Manifest Validation Results:")
    lines.append(f"  Total: {len(results)} capabilities")
    lines.append(f"  Valid: {valid_count}")
    lines.append(f"  Errors: {total_errors}")
    lines.append(f"  Warnings: {total_warnings}")
    lines.append("")

    for result in results:
        if result.valid and not result.warnings:
            lines.append(f"[OK] {result.capability}: Valid")
        elif result.valid and result.warnings:
            lines.append(
                f"[WARN] {result.capability}: Valid with {len(result.warnings)} warning(s)"
            )
            if verbose:
                for w in result.warnings:
                    lines.append(f"   [WARN] {w.field}: {w.message}")
        else:
            lines.append(
                f"[ERROR] {result.capability}: Invalid ({len(result.errors)} error(s))"
            )
            for e in result.errors:
                lines.append(f"   [ERROR] {e.field}: {e.message}")
            if verbose:
                for w in result.warnings:
                    lines.append(f"   [WARN] {w.field}: {w.message}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate capability manifest.yaml files against schema"
    )
    parser.add_argument(
        "paths", nargs="+", type=Path, help="Paths to validate (capability directories)"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show all warnings"
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    args = parser.parse_args()

    all_results = []

    for path in args.paths:
        if not path.exists():
            print(f"Warning: Path does not exist: {path}", file=sys.stderr)
            continue

        results = validate_directory(path)
        all_results.extend(results)

    if args.json:
        import json

        output = {
            "total": len(all_results),
            "valid": sum(1 for r in all_results if r.valid),
            "results": [
                {
                    "capability": r.capability,
                    "valid": r.valid,
                    "errors": [
                        {"field": e.field, "message": e.message} for e in r.errors
                    ],
                    "warnings": [
                        {"field": w.field, "message": w.message} for w in r.warnings
                    ],
                }
                for r in all_results
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_results(all_results, verbose=args.verbose))

    # Exit code
    has_errors = any(not r.valid for r in all_results)
    has_warnings = any(r.warnings for r in all_results)

    if has_errors:
        sys.exit(1)
    elif has_warnings and args.strict:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
