#!/usr/bin/env python3
"""Run the one-shot browser capacity acceptance preflight."""

from pathlib import Path
import sys


LOCAL_CORE_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(LOCAL_CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(LOCAL_CORE_ROOT))


from scripts.maintenance.browser_resource_capacity_preflight_core.cli import (  # noqa: E402
    main,
)


if __name__ == "__main__":
    raise SystemExit(main())
