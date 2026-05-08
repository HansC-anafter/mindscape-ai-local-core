#!/usr/bin/env python3
"""Run Codex login/status/logout against one isolated account-home."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from codex_account_home_auth_inventory import _bootstrap_imports


def _account_home_env(codex_home: str) -> dict[str, str]:
    home = str(codex_home or "").strip()
    return {
        "CODEX_HOME": home,
        "HOME": home,
        "XDG_CONFIG_HOME": str(Path(home) / ".config"),
        "XDG_DATA_HOME": str(Path(home) / ".local" / "share"),
        "XDG_STATE_HOME": str(Path(home) / ".local" / "state"),
    }


def _runtime_rows() -> list[tuple[Any, dict[str, Any]]]:
    from backend.app.services.codex_pool_health import read_health_metadata
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

    service = CodexPoolService()
    db = service._get_db()
    RuntimeEnvironment = service._get_model()
    try:
        rows = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                RuntimeEnvironment.pool_enabled.is_(True),
                RuntimeEnvironment.auth_type.in_(("host_session", "none")),
            )
            .all()
        )
        result: list[tuple[Any, dict[str, Any]]] = []
        for runtime in rows:
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            health = read_health_metadata(
                metadata,
                auth_type=str(getattr(runtime, "auth_type", "") or ""),
            )
            if str(health.get("seed_kind") or "").strip().lower() != "account_home":
                continue
            result.append((runtime, metadata))
        return result
    finally:
        db.close()


def _row_payload(runtime: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_id": str(getattr(runtime, "id", "") or ""),
        "login_email": str(metadata.get("login_email") or "").strip().lower() or None,
        "account_key": str(metadata.get("account_key") or "").strip() or None,
        "codex_home": str(metadata.get("CODEX_HOME") or metadata.get("codex_home") or "").strip()
        or None,
    }


def _resolve_target(args: argparse.Namespace) -> dict[str, Any]:
    if args.codex_home:
        return {
            "runtime_id": None,
            "login_email": args.login_email or None,
            "account_key": args.account_key or None,
            "codex_home": str(Path(args.codex_home).expanduser()),
        }

    rows = _runtime_rows()
    matches: list[dict[str, Any]] = []
    for runtime, metadata in rows:
        payload = _row_payload(runtime, metadata)
        if args.runtime_id and payload["runtime_id"] != args.runtime_id:
            continue
        if args.login_email and payload["login_email"] != args.login_email.lower():
            continue
        if args.account_key and payload["account_key"] != args.account_key:
            continue
        matches.append(payload)

    if not matches:
        raise SystemExit("No matching Codex account-home runtime")
    if len(matches) > 1:
        print(json.dumps({"matches": matches}, indent=2, sort_keys=True), file=sys.stderr)
        raise SystemExit(
            "Multiple account-home runtimes match; pass --runtime-id or --account-key"
        )
    if not matches[0].get("codex_home"):
        raise SystemExit("Matched runtime has no CODEX_HOME")
    return matches[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_argument_group("target")
    selector.add_argument("--runtime-id", default="")
    selector.add_argument("--login-email", default="")
    selector.add_argument("--account-key", default="")
    selector.add_argument("--codex-home", default="")
    parser.add_argument(
        "--action",
        choices=("login", "status", "logout"),
        default="login",
    )
    parser.add_argument("--device-auth", action="store_true")
    parser.add_argument("--codex-binary", default="/Applications/Codex.app/Contents/Resources/codex")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    _bootstrap_imports()
    args = parse_args()
    if args.list:
        print(
            json.dumps(
                [_row_payload(runtime, metadata) for runtime, metadata in _runtime_rows()],
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    target = _resolve_target(args)
    env = os.environ.copy()
    env.update(_account_home_env(str(target["codex_home"])))
    cmd = [args.codex_binary]
    if args.action == "status":
        cmd.extend(["login", "status"])
    elif args.action == "logout":
        cmd.append("logout")
    else:
        cmd.append("login")
        if args.device_auth:
            cmd.append("--device-auth")

    print(json.dumps({"target": target, "cmd": cmd}, indent=2, sort_keys=True))
    if args.dry_run:
        return 0
    return subprocess.run(cmd, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
