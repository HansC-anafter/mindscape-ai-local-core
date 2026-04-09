#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _configure_sys_path() -> None:
    local_core_root = Path(__file__).resolve().parents[1]
    cloud_root = local_core_root.parent / "mindscape-ai-cloud"
    if str(cloud_root) not in sys.path:
        sys.path.insert(0, str(cloud_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-dir", default="")
    parser.add_argument("--viseme-bridge-dir", default="")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _configure_sys_path()
    from capabilities.comfyui_runtime.services.talking_head_repo_contract import (
        inspect_talking_head_repo_contracts,
    )

    payload = inspect_talking_head_repo_contracts(
        backend_dir=args.backend_dir,
        viseme_bridge_dir=args.viseme_bridge_dir,
    )
    if args.json:
        print(json.dumps(payload))
    else:
        print(payload.get("summary_text") or "")
    return 0 if payload.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
