"""Shared constants and small helpers for the PD real IG storyboard E2E."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REFS = [
    "ref_63601788",
    "ref_8849fff0",
    "ref_50eb8376",
    "ref_6702844a",
    "ref_c3f6a15d",
    "ref_9ddb375f",
    "ref_21f1b00a",
    "ref_23953361",
]


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []
