import copy
import threading
import time
from typing import Any, Dict

_CAPABILITY_ROUTE_CACHE_TTL_SECONDS = 300.0
_RUNTIME_UI_INDEX_CACHE_TTL_SECONDS = 60.0
_INSTALLED_PACK_IDS_CACHE_TTL_SECONDS = 300.0
_PACK_META_BY_CODE_CACHE_TTL_SECONDS = 60.0
_capability_route_cache: Dict[tuple[str, str], tuple[float, Any]] = {}
_capability_route_cache_lock = threading.Lock()
_runtime_ui_index_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
_runtime_ui_index_cache_lock = threading.Lock()
_installed_pack_ids_cache: tuple[float, list[str]] | None = None
_installed_pack_ids_cache_lock = threading.Lock()
_pack_meta_by_code_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
_pack_meta_by_code_cache_lock = threading.Lock()


def _clone_payload(payload: Any) -> Any:
    return copy.deepcopy(payload)


def get_cached_capability_route_payload(scope: str, capability_code: str) -> Any | None:
    now = time.monotonic()
    cache_key = (scope, capability_code)
    with _capability_route_cache_lock:
        cached = _capability_route_cache.get(cache_key)
        if not cached:
            return None
        cached_at, payload = cached
        if now - cached_at > _CAPABILITY_ROUTE_CACHE_TTL_SECONDS:
            _capability_route_cache.pop(cache_key, None)
            return None
        return _clone_payload(payload)


def set_cached_capability_route_payload(
    scope: str,
    capability_code: str,
    payload: Any,
) -> None:
    cache_key = (scope, capability_code)
    with _capability_route_cache_lock:
        _capability_route_cache[cache_key] = (
            time.monotonic(),
            _clone_payload(payload),
        )


def get_cached_runtime_ui_index(capability_code: str) -> Dict[str, Any] | None:
    now = time.monotonic()
    with _runtime_ui_index_cache_lock:
        cached = _runtime_ui_index_cache.get(capability_code)
        if not cached:
            return None
        cached_at, payload = cached
        if now - cached_at > _RUNTIME_UI_INDEX_CACHE_TTL_SECONDS:
            _runtime_ui_index_cache.pop(capability_code, None)
            return None
        return _clone_payload(payload)


def set_cached_runtime_ui_index(
    capability_code: str,
    payload: Dict[str, Any],
) -> None:
    with _runtime_ui_index_cache_lock:
        _runtime_ui_index_cache[capability_code] = (
            time.monotonic(),
            _clone_payload(payload),
        )


def get_cached_installed_pack_ids() -> set[str] | None:
    now = time.monotonic()
    with _installed_pack_ids_cache_lock:
        if _installed_pack_ids_cache is None:
            return None
        cached_at, payload = _installed_pack_ids_cache
        if now - cached_at > _INSTALLED_PACK_IDS_CACHE_TTL_SECONDS:
            return None
        return set(payload)


def set_cached_installed_pack_ids(payload: set[str]) -> None:
    with _installed_pack_ids_cache_lock:
        global _installed_pack_ids_cache
        _installed_pack_ids_cache = (
            time.monotonic(),
            sorted(payload),
        )


def get_cached_pack_meta_by_code(capability_code: str) -> Dict[str, Any] | None:
    now = time.monotonic()
    with _pack_meta_by_code_cache_lock:
        cached = _pack_meta_by_code_cache.get(capability_code)
        if not cached:
            return None
        cached_at, payload = cached
        if now - cached_at > _PACK_META_BY_CODE_CACHE_TTL_SECONDS:
            _pack_meta_by_code_cache.pop(capability_code, None)
            return None
        return _clone_payload(payload)


def set_cached_pack_meta_by_code(
    capability_code: str,
    payload: Dict[str, Any],
) -> None:
    with _pack_meta_by_code_cache_lock:
        _pack_meta_by_code_cache[capability_code] = (
            time.monotonic(),
            _clone_payload(payload),
        )


def clear_installed_capability_route_cache() -> None:
    with _capability_route_cache_lock:
        _capability_route_cache.clear()
    with _runtime_ui_index_cache_lock:
        _runtime_ui_index_cache.clear()
    with _installed_pack_ids_cache_lock:
        global _installed_pack_ids_cache
        _installed_pack_ids_cache = None
    with _pack_meta_by_code_cache_lock:
        _pack_meta_by_code_cache.clear()
