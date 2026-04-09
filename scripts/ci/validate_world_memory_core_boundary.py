#!/usr/bin/env python3
"""
CI guard for the local-core world_memory_core boundary.

world_memory_core is a local-core system module. The capability install tree
must not contain a tracked or authoring copy under backend/app/capabilities/.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CAPABILITY_ROOT = REPO_ROOT / "backend/app/capabilities/world_memory_core"
SOURCE_ROOT = REPO_ROOT / "backend/app/system_capabilities/world_memory_core"


def _error(message: str) -> str:
    return f"[world-memory-core-boundary] {message}"


def main() -> int:
    errors: list[str] = []

    if not SOURCE_ROOT.exists():
        errors.append(
            _error(
                f"Missing system source root: {SOURCE_ROOT.relative_to(REPO_ROOT)}"
            )
        )

    if CAPABILITY_ROOT.exists():
        actual_capability_files = [
            path.relative_to(REPO_ROOT)
            for path in CAPABILITY_ROOT.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and not path.name.startswith(".")
        ]
        if actual_capability_files:
            errors.append(
                _error(
                    "backend/app/capabilities/world_memory_core must stay empty; found: "
                    + ", ".join(str(path) for path in sorted(actual_capability_files))
                )
            )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("world_memory_core boundary OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
