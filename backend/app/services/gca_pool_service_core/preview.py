"""Safe GCA pool preview selection helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.services.gca_pool_service_core.account_state import (
    is_account_available,
    is_account_cooling,
    parse_iso_timestamp,
    pool_sort_key,
)


def build_active_runtime_preview(
    accounts: List[Dict[str, Any]],
    preferred_runtime_id: Optional[str] = None,
    allow_runtime_substitution: bool = False,
) -> Dict[str, Any]:
    """Return a safe, non-secret preview of current pool selection."""
    now = datetime.now(timezone.utc)

    available_accounts = sorted(
        [account for account in accounts if is_account_available(account, now)],
        key=pool_sort_key,
    )
    cooling_accounts = sorted(
        [account for account in accounts if is_account_cooling(account, now)],
        key=lambda account: parse_iso_timestamp(account.get("cooldown_until"))
        or datetime.max.replace(tzinfo=timezone.utc),
    )

    preferred_account = None
    if not preferred_runtime_id and not allow_runtime_substitution:
        return {
            "error": "No preferred GCA runtime configured; runtime substitution is disabled.",
            "selected_runtime_id": None,
            "account": None,
            "status": "unavailable",
            "available_count": len(available_accounts),
            "cooling_count": len(cooling_accounts),
            "pool_count": len(accounts),
            "next_reset_at": cooling_accounts[0]["cooldown_until"] if cooling_accounts else None,
        }
    if preferred_runtime_id:
        preferred_account = next(
            (account for account in accounts if account["id"] == preferred_runtime_id),
            None,
        )
        if preferred_account and is_account_available(preferred_account, now):
            return {
                "selected_runtime_id": preferred_account["id"],
                "account": preferred_account,
                "status": "available",
                "available_count": len(available_accounts),
                "cooling_count": len(cooling_accounts),
                "pool_count": len(accounts),
                "next_reset_at": (
                    cooling_accounts[0]["cooldown_until"] if cooling_accounts else None
                ),
            }
        if preferred_runtime_id and not allow_runtime_substitution:
            cooldown_until = (
                preferred_account.get("cooldown_until") if preferred_account else None
            )
            return {
                "error": f"Preferred GCA runtime unavailable: {preferred_runtime_id}",
                "selected_runtime_id": None,
                "account": preferred_account,
                "status": (
                    "cooldown"
                    if preferred_account and is_account_cooling(preferred_account, now)
                    else "unavailable"
                ),
                "cooldown_until": cooldown_until,
                "available_count": len(available_accounts),
                "cooling_count": len(cooling_accounts),
                "pool_count": len(accounts),
                "next_reset_at": cooldown_until
                or (cooling_accounts[0]["cooldown_until"] if cooling_accounts else None),
            }

    if available_accounts:
        selected = available_accounts[0]
        result: Dict[str, Any] = {
            "selected_runtime_id": selected["id"],
            "account": selected,
            "status": "available",
            "available_count": len(available_accounts),
            "cooling_count": len(cooling_accounts),
            "pool_count": len(accounts),
            "next_reset_at": (
                cooling_accounts[0]["cooldown_until"] if cooling_accounts else None
            ),
        }
        if preferred_account and preferred_runtime_id and preferred_account["id"] != selected["id"]:
            result["preferred_runtime_id"] = preferred_runtime_id
            result["preferred_status"] = (
                "cooldown"
                if is_account_cooling(preferred_account, now)
                else "unavailable"
            )
        return result

    return {
        "error": "No enabled GCA pool account is currently available",
        "selected_runtime_id": None,
        "account": None,
        "status": "unavailable",
        "available_count": 0,
        "cooling_count": len(cooling_accounts),
        "pool_count": len(accounts),
        "next_reset_at": cooling_accounts[0]["cooldown_until"] if cooling_accounts else None,
    }
