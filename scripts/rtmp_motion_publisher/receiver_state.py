from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


__all__ = ["transition_receiver_state"]
