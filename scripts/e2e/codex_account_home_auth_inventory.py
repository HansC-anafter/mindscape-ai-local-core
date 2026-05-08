#!/usr/bin/env python3
"""Print materialized Codex account-home auth source inventory."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_dotenv_defaults(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _host_reachable_database_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.hostname != "postgres":
        return raw_url
    host_port = os.getenv("PD_E2E_POSTGRES_HOST_PORT", "5433").strip() or "5433"
    username = parsed.username or ""
    password = f":{parsed.password}" if parsed.password else ""
    auth = f"{username}{password}@" if username else ""
    return urlunparse(parsed._replace(netloc=f"{auth}localhost:{host_port}"))


def _bootstrap_imports() -> None:
    repo = _repo_root()
    _load_dotenv_defaults(repo / ".env")
    for key in ("DATABASE_URL_CORE", "DATABASE_URL_VECTOR", "DATABASE_URL"):
        value = os.environ.get(key)
        if value:
            os.environ[key] = _host_reachable_database_url(value)
    for path in (repo, repo / "backend"):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emails", nargs="*", default=[])
    parser.add_argument("--format", choices=("json",), default="json")
    parser.add_argument("--persist-runtime-metadata", action="store_true")
    return parser.parse_args()


def main() -> int:
    _bootstrap_imports()
    args = parse_args()
    from backend.app.services.codex_account_home_auth_source_service import (
        CodexAccountHomeAuthSourceService,
    )

    payload: dict[str, Any] = {
        "status": "ok",
        "sources": CodexAccountHomeAuthSourceService().inventory_sources(
            emails={
                str(email or "").strip().lower()
                for email in args.emails
                if str(email or "").strip()
            },
            persist_runtime_metadata=bool(args.persist_runtime_metadata),
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
