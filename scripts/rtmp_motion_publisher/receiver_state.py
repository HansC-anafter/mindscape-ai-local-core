from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_STABLE_REASON = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")


def safe_receiver_failure_reason(exc: Exception) -> str:
    message = str(exc).strip()
    if isinstance(exc, ValueError) and _STABLE_REASON.fullmatch(message):
        return message
    if isinstance(exc, OSError):
        errno = exc.errno if isinstance(exc.errno, int) else "unknown"
        return f"live_media_receiver_os_error_{errno}"
    return "live_media_receiver_runtime_failed"


def transition_receiver_state(
    args: Any,
    state: str,
    *,
    reason: str | None = None,
) -> None:
    raw_path = str(getattr(args, "receiver_state_path", "") or "").strip()
    if not raw_path:
        return
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "schema_version": "live_media_receiver_state.v1",
        "workspace_id": str(args.workspace_id),
        "media_session_id": str(getattr(args, "media_session_id", "")),
        "receiver_identity": str(getattr(args, "receiver_identity", "")),
        "pid": os.getpid(),
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if reason:
        payload["reason"] = reason[:500]
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


__all__ = ["safe_receiver_failure_reason", "transition_receiver_state"]
