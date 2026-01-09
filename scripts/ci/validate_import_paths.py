#!/usr/bin/env python3
"""
CI Script: Validate Import Paths

Wrapper around `mindscape-playbook-tools` validator.
"""

import sys
import argparse
from pathlib import Path

try:
    from mindscape_playbook_tools.validators.import_paths import validate_import_paths

    HAS_KIT = True
except ImportError:
    HAS_KIT = False


def main():
    parser = argparse.ArgumentParser(
        description="Validate capability import paths (via mindscape-playbook-tools)"
    )
    parser.add_argument(
        "paths", nargs="+", type=Path, help="Paths to validate (capability directories)"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors"
    )

    args = parser.parse_args()

    if not HAS_KIT:
        print("Error: mindscape-playbook-tools not installed.", file=sys.stderr)
        print("Please run: pip install mindscape-playbook-tools", file=sys.stderr)
        sys.exit(1)

    has_errors = False

    for path in args.paths:
        if not path.exists():
            print(f"Warning: Path does not exist: {path}", file=sys.stderr)
            continue

        print(f"Validating imports in {path}...")

        result = validate_import_paths(path, strict=args.strict)

        if result.errors:
            for error in result.errors:
                print(f"[ERROR] {error}")
            has_errors = True

        if result.warnings:
            for warning in result.warnings:
                print(f"[WARN] {warning}")
            if args.strict:
                has_errors = True

    if has_errors:
        sys.exit(1)

    print("All import paths are valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
