#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from laf_host_runtime_common import default_runtime_root, venv_python


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default=str(default_runtime_root()))
    parser.add_argument("--image-path", default="")
    parser.add_argument("--image-url", default="")
    parser.add_argument("--mask-path", default="")
    parser.add_argument("--mask-url", default="")
    parser.add_argument("--strategy", default="conservative")
    parser.add_argument("--impact-region-bbox-json", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime_root = Path(args.runtime_root).expanduser()
    python_bin = venv_python(runtime_root)
    worker = Path(__file__).with_name("laf_lama_completion_worker.py")

    if not python_bin.exists():
        print(
            json.dumps(
                {
                    "status": "error",
                    "returncode": 1,
                    "stderr": f"Runtime venv python not found: {python_bin}",
                }
            )
        )
        return 0

    command = [
        str(python_bin),
        str(worker),
        "--strategy",
        str(args.strategy or "conservative"),
    ]
    if args.image_path:
        command.extend(["--image-path", args.image_path])
    if args.image_url:
        command.extend(["--image-url", args.image_url])
    if args.mask_path:
        command.extend(["--mask-path", args.mask_path])
    if args.mask_url:
        command.extend(["--mask-url", args.mask_url])
    if args.impact_region_bbox_json:
        command.extend(["--impact-region-bbox-json", args.impact_region_bbox_json])

    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "1",
        },
    )

    stdout = (process.stdout or "").strip()
    stderr = (process.stderr or "").strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                payload.setdefault("returncode", process.returncode)
                payload.setdefault("stderr", stderr)
                print(json.dumps(payload))
                return 0
        except json.JSONDecodeError:
            pass

    print(
        json.dumps(
            {
                "status": "error",
                "returncode": process.returncode,
                "stderr": stderr or stdout or "LaMa host worker failed",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
