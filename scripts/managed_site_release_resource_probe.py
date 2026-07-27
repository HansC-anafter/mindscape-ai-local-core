#!/usr/bin/env python3
"""Bounded JSON facade for managed site release resource evidence."""

from __future__ import annotations

import json
import sys
from typing import Any

from scripts.managed_site_release_resource_probe_core import (
    ManagedSiteReleaseResourceProbeFacade,
)

MAX_INPUT_BYTES = 4 * 1024 * 1024


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("managed_resource_probe_input_too_large")
        request = json.loads(raw)
        result = ManagedSiteReleaseResourceProbeFacade().execute(
            request
        )
        sys.stdout.write(canonical_json(result) + "\n")
        return 0
    except Exception as exc:
        sys.stdout.write(
            canonical_json(
                {
                    "success": False,
                    "error_code": str(exc).split(":", 1)[0],
                }
            )
            + "\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
