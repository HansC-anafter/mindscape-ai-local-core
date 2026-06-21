#!/usr/bin/env python3
"""Validate mirrored product semantic traceability helper parity."""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCAL_HELPER = "scripts/ci/product_semantic_traceability.py"
DEFAULT_CANONICAL_HELPER = (
    ".contract-sources/mindscape-ai-cloud/scripts/product_semantic_traceability.py"
)


def _read_normalized(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def validate_helper_parity(
    *,
    local_helper: Path,
    canonical_helper: Path,
) -> list[str]:
    errors: list[str] = []
    if not local_helper.exists():
        return [f"Local product semantic traceability helper is missing: {local_helper}"]
    if not canonical_helper.exists():
        return [f"Canonical product semantic traceability helper is missing: {canonical_helper}"]

    local_source = _read_normalized(local_helper)
    canonical_source = _read_normalized(canonical_helper)
    if local_source == canonical_source:
        return errors

    diff = "".join(
        difflib.unified_diff(
            canonical_source.splitlines(keepends=True),
            local_source.splitlines(keepends=True),
            fromfile=str(canonical_helper),
            tofile=str(local_helper),
        )
    )
    errors.append(
        "Product semantic traceability helper parity drift detected. "
        "Sync the local mirrored helper from the cloud canonical helper.\n"
        f"{diff}"
    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--local-helper", default=DEFAULT_LOCAL_HELPER)
    parser.add_argument("--canonical-helper", default=DEFAULT_CANONICAL_HELPER)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    local_helper_arg = Path(args.local_helper)
    canonical_helper_arg = Path(args.canonical_helper)
    local_helper = (
        local_helper_arg if local_helper_arg.is_absolute() else repo_root / local_helper_arg
    )
    canonical_helper = (
        canonical_helper_arg
        if canonical_helper_arg.is_absolute()
        else repo_root / canonical_helper_arg
    )

    errors = validate_helper_parity(
        local_helper=local_helper,
        canonical_helper=canonical_helper,
    )
    if errors:
        print("Product semantic traceability helper parity failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Product semantic traceability helper parity passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
