#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.app.services.codex_pool_service import CodexPoolService  # noqa: E402
from backend.app.services.external_agents.bridge.codex_cli_runner import (  # noqa: E402
    resolve_codex_cli_binary,
    resolve_codex_cli_cwd,
    run_codex_cli_subprocess,
)


def _default_task(mode: str) -> str:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode == "planner":
        return (
            "[Meeting Agent Turn]\n"
            "Session: codex-runtime-probe\n"
            "Follow the system instructions and produce a direct role response.\n\n"
            "[System Prompt]\n"
            "你是會議 planner。請輸出簡潔、可執行、具體的中文規劃。\n\n"
            "[Turn Prompt]\n"
            "請只根據這個高層意圖，給出單輪可執行的 planner 回應：\n"
            "- 用單一鏡位表達一個室內台面上的托盤交接。\n"
            "- 讓會議自己決定角色、物件、錨點、走位、鏡位與節奏。\n"
            "- 輸出要能供 spatial schedule 消費。\n"
        )
    return "Reply with exactly OK."


async def _probe_runtime(
    *,
    runtime_id: str,
    task: str,
    timeout: float,
    stall_timeout: float,
    model: str | None,
    codex_home: str | None,
    home: str | None,
) -> dict[str, Any]:
    if codex_home:
        bundle = {
            "selected_runtime_id": runtime_id,
            "runtime_health_state": None,
            "runtime_seed_kind": None,
            "env": {
                "CODEX_HOME": codex_home,
                "HOME": home or str(Path(codex_home).parent.parent),
            },
        }
    else:
        bundle = CodexPoolService(requalification_runner=lambda: None).get_active_auth_bundle(
            preferred_runtime_id=runtime_id,
            allow_runtime_substitution=False,
        )
    if "env" not in bundle:
        return {
            "runtime_id": runtime_id,
            "ok": False,
            "error": bundle.get("error") or "bundle_unavailable",
            "bundle": bundle,
        }

    binary = resolve_codex_cli_binary(os.environ.get("CODEX_CLI_PATH", "").strip())
    cwd = resolve_codex_cli_cwd(str(REPO_ROOT))
    cmd = [
        binary,
        "-c",
        'model_reasoning_effort="medium"',
        "exec",
        "--skip-git-repo-check",
        "--full-auto",
    ]
    with tempfile.NamedTemporaryFile(
        prefix=f"codex_canary_{runtime_id}_",
        suffix=".txt",
        delete=False,
    ) as tmp:
        last_message_path = tmp.name
    cmd.extend(["--output-last-message", last_message_path])
    if model:
        cmd.extend(["--model", model])
    cmd.append(task)

    env = dict(os.environ)
    env.update({str(k): str(v) for k, v in dict(bundle.get("env") or {}).items()})

    try:
        result = await run_codex_cli_subprocess(
            cmd=cmd,
            cwd=cwd,
            env=env,
            last_message_path=last_message_path,
            execution_id=f"codex-runtime-probe:{runtime_id}",
            timeout=timeout,
            stall_timeout=stall_timeout,
        )
        return {
            "runtime_id": runtime_id,
            "ok": result.returncode == 0 and bool(result.output_text),
            "returncode": result.returncode,
            "output_text": result.output_text,
            "stderr_text": result.stderr_text,
            "stdout_text": result.stdout_text,
            "combined_output": result.combined_output,
            "synthesized_error": result.synthesized_error,
            "selected_runtime_id": bundle.get("selected_runtime_id"),
            "runtime_health_state": bundle.get("runtime_health_state"),
            "runtime_seed_kind": bundle.get("runtime_seed_kind"),
            "env": bundle.get("env"),
        }
    except Exception as exc:
        return {
            "runtime_id": runtime_id,
            "ok": False,
            "error": str(exc),
            "selected_runtime_id": bundle.get("selected_runtime_id"),
            "runtime_health_state": bundle.get("runtime_health_state"),
            "runtime_seed_kind": bundle.get("runtime_seed_kind"),
            "env": bundle.get("env"),
        }
    finally:
        try:
            os.unlink(last_message_path)
        except OSError:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe a Codex pool runtime with a live canary")
    parser.add_argument("--runtime-id", action="append", required=True)
    parser.add_argument(
        "--runtime-home",
        action="append",
        default=[],
        help="Optional explicit mapping runtime_id=/abs/CODEX_HOME to avoid DB lookup",
    )
    parser.add_argument("--home", help="Optional HOME override when using --runtime-home")
    parser.add_argument("--mode", choices=("ok", "planner"), default="planner")
    parser.add_argument("--task-file", type=Path)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--stall-timeout", type=float, default=60.0)
    parser.add_argument("--model", help="Optional explicit Codex model")
    return parser.parse_args()


async def _main() -> int:
    args = parse_args()
    task = (
        args.task_file.read_text(encoding="utf-8")
        if args.task_file
        else _default_task(args.mode)
    )
    runtime_homes: dict[str, str] = {}
    for raw_entry in args.runtime_home:
        runtime_id, separator, path_value = str(raw_entry or "").partition("=")
        if not separator or not runtime_id.strip() or not path_value.strip():
            raise SystemExit(f"Invalid --runtime-home entry: {raw_entry!r}")
        runtime_homes[runtime_id.strip()] = path_value.strip()
    results = []
    for runtime_id in args.runtime_id:
        results.append(
            await _probe_runtime(
                runtime_id=str(runtime_id or "").strip(),
                task=task,
                timeout=float(args.timeout),
                stall_timeout=float(args.stall_timeout),
                model=args.model,
                codex_home=runtime_homes.get(str(runtime_id or "").strip()),
                home=args.home,
            )
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
