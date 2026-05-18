import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from fastapi import HTTPException

from .schemas import WorkspaceAgentAuthActionRequest


def _account_home_env(codex_home: str) -> Dict[str, str]:
    home = str(codex_home or "").strip()
    if not home:
        return {}
    return {
        "CODEX_HOME": home,
        "HOME": home,
        "XDG_CONFIG_HOME": str(Path(home) / ".config"),
        "XDG_DATA_HOME": str(Path(home) / ".local" / "share"),
        "XDG_STATE_HOME": str(Path(home) / ".local" / "state"),
    }


def _default_codex_account_home_root() -> Path:
    configured = str(
        os.environ.get("MINDSCAPE_CODEX_ACCOUNT_HOME_POOL_ROOT") or ""
    ).strip()
    if configured:
        return Path(os.path.expanduser(configured))
    return Path.home() / ".mindscape" / "runtime" / "codex-home-pool" / "accounts"


def _new_codex_account_home_path() -> str:
    return str(_default_codex_account_home_root() / f"acct-{uuid.uuid4().hex[:16]}")


def _normalize_codex_home_path(codex_home: str) -> Path:
    raw = str(codex_home or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="codex_home is required.")
    return Path(os.path.expanduser(raw)).resolve(strict=False)


def _is_managed_codex_account_home(path: Path) -> bool:
    parts = path.parts
    if path.name.startswith("acct-") is False:
        return False
    if len(parts) < 3:
        return False
    return parts[-2] == "accounts" and parts[-3] == "codex-home-pool"


def _ensure_codex_account_home_dirs(codex_home: str) -> Path:
    home_path = _normalize_codex_home_path(codex_home)
    if not _is_managed_codex_account_home(home_path):
        raise HTTPException(
            status_code=400,
            detail=(
                "Codex account-home paths must be managed pool paths ending in "
                "codex-home-pool/accounts/acct-*."
            ),
        )
    if home_path.exists() and home_path.is_symlink():
        raise HTTPException(
            status_code=409,
            detail=f"Refusing to use symlinked Codex account home: {home_path}",
        )
    home_path.mkdir(parents=True, exist_ok=True)
    for child in (
        ".config",
        ".local/share",
        ".local/state",
    ):
        (home_path / child).mkdir(parents=True, exist_ok=True)
    seed_path = home_path / ".mindscape-seed.json"
    if not seed_path.exists():
        seed_path.write_text(
            json.dumps(
                {
                    "account_home": True,
                    "created_by": "mindscape-local-core",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return home_path


def _has_codex_account_home_target(
    payload: Optional[WorkspaceAgentAuthActionRequest],
) -> bool:
    if payload is None:
        return False
    return any(
        str(getattr(payload, key, None) or "").strip()
        for key in ("runtime_id", "login_email", "account_key", "codex_home")
    )
