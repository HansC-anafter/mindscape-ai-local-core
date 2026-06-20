"""GCA pool account state helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def count_recent_errors(runtime) -> int:
    """Count consecutive quota errors for backoff calculation."""
    if not runtime.last_error_code or runtime.last_error_code != "429":
        return 0
    if not runtime.cooldown_until:
        return 0
    return 1


def to_pool_dict(runtime) -> Dict[str, Any]:
    """Convert runtime to pool-specific dict."""
    identity = None
    if runtime.auth_status == "connected" and runtime.auth_config:
        identity = runtime.auth_config.get("identity")
    return {
        "id": runtime.id,
        "email": identity,
        "auth_status": runtime.auth_status or "disconnected",
        "pool_enabled": runtime.pool_enabled,
        "pool_priority": runtime.pool_priority,
        "cooldown_until": (
            runtime.cooldown_until.isoformat() if runtime.cooldown_until else None
        ),
        "last_used_at": (
            runtime.last_used_at.isoformat() if runtime.last_used_at else None
        ),
        "last_error_code": runtime.last_error_code,
    }


def parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp and default naive values to UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_account_cooling(
    account: Dict[str, Any],
    now: datetime,
) -> bool:
    """Return whether a pool account is still in cooldown."""
    cooldown_until = parse_iso_timestamp(account.get("cooldown_until"))
    return bool(cooldown_until and cooldown_until > now)


def is_account_available(
    account: Dict[str, Any],
    now: datetime,
) -> bool:
    """Return whether a pool account can be selected now."""
    return (
        account.get("pool_enabled") is True
        and account.get("auth_status") in ("connected", "expired")
        and not is_account_cooling(account, now)
    )


def pool_sort_key(account: Dict[str, Any]) -> tuple[Any, datetime]:
    """Sort pool accounts by configured priority and least recent use."""
    last_used_at = parse_iso_timestamp(account.get("last_used_at"))
    if last_used_at is None:
        last_used_at = datetime.fromtimestamp(0, tz=timezone.utc)
    return (account.get("pool_priority", 0), last_used_at)
