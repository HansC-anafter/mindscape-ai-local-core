"""
Capability Hot Reload Manager

Reloads capability registries and feature pack routes without restarting the backend.
Feature-flagged via ENABLE_CAPABILITY_HOT_RELOAD=1.
"""

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from fastapi import FastAPI

from backend.app.capabilities.api_loader import load_capability_apis
from backend.app.capabilities.registry import load_capabilities
from backend.app.core.pack_registry import load_and_register_packs

logger = logging.getLogger(__name__)

_RELOAD_LOCK = threading.Lock()
_STATE_KEY = "capability_hot_reload_state"


def hot_reload_enabled() -> bool:
    return os.getenv("ENABLE_CAPABILITY_HOT_RELOAD") == "1"


def _get_state(app: FastAPI) -> Dict[str, List[Any]]:
    state = getattr(app.state, _STATE_KEY, None)
    if state is None:
        state = {"pack_routes": [], "capability_api_routes": []}
        setattr(app.state, _STATE_KEY, state)
    return state


def _remove_routes(app: FastAPI, routes: List[Any]) -> int:
    if not routes:
        return 0
    current_routes = list(app.router.routes)
    remaining = [route for route in current_routes if route not in routes]
    removed = len(current_routes) - len(remaining)
    app.router.routes = remaining
    routes.clear()
    return removed


def _get_allowlist_from_env() -> Optional[List[str]]:
    allowlist_env = os.getenv("CAPABILITY_ALLOWLIST")
    if not allowlist_env:
        return None
    return [item.strip() for item in allowlist_env.split(",") if item.strip()]


def reload_capability_routes(app: FastAPI, reason: str = "manual") -> Dict[str, Any]:
    """
    Reload capability registry, pack routes, and capability API routes.

    This is a sync function; callers in async contexts should run it in a threadpool.
    """
    if not hot_reload_enabled():
        return {"enabled": False, "reason": reason}

    with _RELOAD_LOCK:
        logger.info(f"Hot reload starting ({reason})")
        state = _get_state(app)

        removed_pack_routes = _remove_routes(app, state["pack_routes"])
        removed_api_routes = _remove_routes(app, state["capability_api_routes"])

        load_capabilities(reset=True)

        added_pack_routes = load_and_register_packs(
            app, route_collector=state["pack_routes"]
        )

        allowlist = _get_allowlist_from_env()
        load_capability_apis(
            app=app,
            allowlist=allowlist,
            enable_all=False,
            route_collector=state["capability_api_routes"],
        )

        logger.info(
            "Hot reload finished: "
            f"removed_pack_routes={removed_pack_routes}, "
            f"removed_capability_api_routes={removed_api_routes}, "
            f"added_pack_routes={len(added_pack_routes)}"
        )

        return {
            "enabled": True,
            "reason": reason,
            "removed_pack_routes": removed_pack_routes,
            "removed_capability_api_routes": removed_api_routes,
            "added_pack_routes": len(added_pack_routes),
            "added_capability_api_routes": len(state["capability_api_routes"]),
        }
