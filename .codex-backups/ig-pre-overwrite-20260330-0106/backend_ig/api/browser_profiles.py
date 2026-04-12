"""
IG Browser Profiles API.

Keep profile listing local-only so the session picker never blocks on IG web API
requests or rate limits.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IG Browser Profiles"])

PROFILES_ROOT = Path("/app/data/ig-browser-profiles")


def _read_storage_state(storage_state_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(storage_state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _collect_profile_info(entry: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "name": entry.name,
        "path": str(entry),
        "logged_in": False,
        "session_expired": False,
        "ig_username": None,
        "ig_user_id": None,
        "ig_cookie_count": 0,
        "username_source": None,
    }

    storage_state_path = entry / "storage_state.json"
    if not storage_state_path.exists():
        return info

    state = _read_storage_state(storage_state_path)
    if not state:
        return info

    cookies = state.get("cookies", [])
    ig_cookies = [c for c in cookies if "instagram" in c.get("domain", "")]
    info["ig_cookie_count"] = len(ig_cookies)

    sessionid_cookie = next(
        (
            c
            for c in cookies
            if c.get("name") == "sessionid" and "instagram" in c.get("domain", "")
        ),
        None,
    )
    if sessionid_cookie:
        expires = sessionid_cookie.get("expires", 0)
        expired = bool(expires and expires > 0 and expires < time.time())
        info["session_expired"] = expired
        info["logged_in"] = not expired

    ds_user = next(
        (
            c
            for c in cookies
            if c.get("name") == "ds_user_id" and "instagram" in c.get("domain", "")
        ),
        None,
    )
    ds_user_id = ds_user.get("value") if ds_user else None
    if ds_user_id:
        info["ig_user_id"] = ds_user_id

    # Keep listing local-only. Do not call IG here; repeated remote lookups can
    # stall the endpoint and re-trigger rate limits while the UI is loading.
    return info


@router.get("/browser-profiles")
async def list_browser_profiles():
    """List all IG browser profiles with local session metadata only."""
    if not PROFILES_ROOT.exists() or not PROFILES_ROOT.is_dir():
        return {"profiles": []}

    result = []
    for entry in sorted(PROFILES_ROOT.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        result.append(_collect_profile_info(entry))

    return {"profiles": result}


@router.get("/browser-profile-status")
async def get_browser_profile_status(
    profile_name: str = Query("default", description="Profile name to check"),
    profile_path: Optional[str] = Query(
        None, description="Optional profile path to check (absolute or under /app)"
    ),
):
    """Check the status of a browser profile for IG automation."""
    import time as _time

    if profile_path:
        if not profile_path.startswith("/"):
            profile_path = f"/app/{profile_path}"
        profile_dir = Path(profile_path)
        try:
            profile_dir.resolve().relative_to(Path("/app").resolve())
        except ValueError:
            return {
                "exists": False,
                "ready": False,
                "logged_in": False,
                "profile_path": str(profile_dir),
                "path_source": "profile_path",
                "message": "Profile path must be under /app",
                "ig_cookies": [],
            }
        path_source = "profile_path"
    else:
        profile_dir = PROFILES_ROOT / profile_name
        path_source = "profile_name"

    if not profile_dir.exists():
        return {
            "exists": False,
            "ready": False,
            "logged_in": False,
            "profile_path": str(profile_dir),
            "path_source": path_source,
            "message": "Profile directory does not exist",
            "ig_cookies": [],
        }

    storage_state_path = profile_dir / "storage_state.json"

    if not storage_state_path.exists():
        return {
            "exists": True,
            "ready": False,
            "logged_in": False,
            "profile_path": str(profile_dir),
            "path_source": path_source,
            "storage_state_path": str(storage_state_path),
            "message": "No storage_state.json found (not logged in)",
            "ig_cookies": [],
        }

    try:
        with open(storage_state_path, "r", encoding="utf-8") as f:
            storage_state = json.load(f)
    except Exception as e:
        return {
            "exists": True,
            "ready": False,
            "logged_in": False,
            "profile_path": str(profile_dir),
            "path_source": path_source,
            "storage_state_path": str(storage_state_path),
            "message": f"Error reading storage_state.json: {e}",
            "ig_cookies": [],
        }

    all_cookies = storage_state.get("cookies", [])
    ig_cookies = [
        {"name": c.get("name"), "domain": c.get("domain")}
        for c in all_cookies
        if "instagram" in c.get("domain", "")
    ]

    sessionid_cookie = None
    for c in all_cookies:
        if c.get("name") == "sessionid" and "instagram" in c.get("domain", ""):
            sessionid_cookie = c
            break

    has_sessionid = sessionid_cookie is not None
    session_expired = False

    if has_sessionid:
        expires = sessionid_cookie.get("expires", 0)
        if expires and expires > 0 and expires < _time.time():
            session_expired = True

    logged_in = has_sessionid and not session_expired

    if logged_in:
        message = "Logged in and ready"
    elif session_expired:
        message = "Session expired — sessionid cookie past expiry. Please re-login."
    else:
        message = (
            f"Profile exists with {len(ig_cookies)} IG cookies "
            f"but NO sessionid (not logged in)"
        )

    return {
        "exists": True,
        "ready": logged_in,
        "logged_in": logged_in,
        "profile_path": str(profile_dir),
        "path_source": path_source,
        "has_sessionid": has_sessionid,
        "sessionid_cookie": sessionid_cookie,
        "session_expired": session_expired,
        "storage_state_path": str(storage_state_path),
        "session_source": "storage_state" if has_sessionid else "none",
        "ig_cookie_count": len(ig_cookies),
        "ig_cookies": ig_cookies,
        "message": message,
    }
