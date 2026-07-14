from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_EVENT_LOG_PATH: Path | None = None


def configure_event_log(path: str | None) -> None:
    global _EVENT_LOG_PATH
    if not path:
        _EVENT_LOG_PATH = None
        return
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _EVENT_LOG_PATH = log_path


def emit(payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    print(line, flush=True)
    if _EVENT_LOG_PATH is not None:
        with _EVENT_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")
