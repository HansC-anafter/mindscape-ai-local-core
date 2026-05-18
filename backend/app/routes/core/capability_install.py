"""
Capability Install Routes compatibility entrypoint.
"""

from contextlib import contextmanager

from fastapi import HTTPException

from backend.app.core.backend_runtime_mode import (
    is_execution_plane,
    should_allow_implicit_pack_reload,
)
from .capability_install_core import paths as _paths
from .capability_install_core import routes as _routes
from .capability_install_core.paths import (
    OVERWRITE_CONFIRMATION_PHRASE,
    OVERWRITE_REVIEW_CONFIRMATION_PHRASE,
    _build_dirty_overwrite_detail,
    _control_plane_install_base_url,
    _ensure_sys_path,
    _handle_dev_mode_reload_trigger,
    _inspect_auto_reload_blockers,
    _parse_bool_flag,
    _require_control_plane_install,
    _require_explicit_overwrite_confirmation,
    _resolve_local_core_root,
    _resolve_runtime_temp_dir,
    _supports_file_touch_reload,
    _utc_now,
)
from .capability_install_core.pipeline import run_install_pipeline
from .capability_install_core.registry_sync import (
    _defer_restart_webhook_if_blocked,
    _schedule_pack_validation_on_current_loop,
    _set_validation_followup_result,
    _should_run_restart_webhook,
    _sync_install_time_registries,
)
from .capability_install_core.routes import install_from_cloud, install_from_file, router
from .capability_install_core.schemas import (
    InstallFromCloudRequest,
    InstallPipelineResult,
    InstallRegistrySyncState,
)


@contextmanager
def _patched_core_path_helpers_for_compat():
    originals = {
        "_inspect_auto_reload_blockers": _paths._inspect_auto_reload_blockers,
        "_supports_file_touch_reload": _paths._supports_file_touch_reload,
        "is_execution_plane": _paths.is_execution_plane,
        "should_allow_implicit_pack_reload": _paths.should_allow_implicit_pack_reload,
    }
    _paths._inspect_auto_reload_blockers = _inspect_auto_reload_blockers
    _paths._supports_file_touch_reload = _supports_file_touch_reload
    _paths.is_execution_plane = is_execution_plane
    _paths.should_allow_implicit_pack_reload = should_allow_implicit_pack_reload
    try:
        yield
    finally:
        _paths._inspect_auto_reload_blockers = originals["_inspect_auto_reload_blockers"]
        _paths._supports_file_touch_reload = originals["_supports_file_touch_reload"]
        _paths.is_execution_plane = originals["is_execution_plane"]
        _paths.should_allow_implicit_pack_reload = originals[
            "should_allow_implicit_pack_reload"
        ]


def _handle_dev_mode_reload_trigger(*args, **kwargs):
    """Compatibility wrapper preserving monkeypatchable legacy module globals."""
    with _patched_core_path_helpers_for_compat():
        return _paths._handle_dev_mode_reload_trigger(*args, **kwargs)


async def install_from_file(*args, **kwargs):
    """Compatibility wrapper for tests and legacy imports."""
    with _patched_core_path_helpers_for_compat():
        return await _routes.install_from_file(*args, **kwargs)


async def install_from_cloud(*args, **kwargs):
    """Compatibility wrapper for tests and legacy imports."""
    with _patched_core_path_helpers_for_compat():
        return await _routes.install_from_cloud(*args, **kwargs)

__all__ = [
    "router",
    "OVERWRITE_CONFIRMATION_PHRASE",
    "OVERWRITE_REVIEW_CONFIRMATION_PHRASE",
    "InstallPipelineResult",
    "InstallRegistrySyncState",
    "InstallFromCloudRequest",
    "HTTPException",
    "is_execution_plane",
    "should_allow_implicit_pack_reload",
    "_utc_now",
    "_resolve_local_core_root",
    "_ensure_sys_path",
    "_resolve_runtime_temp_dir",
    "_supports_file_touch_reload",
    "_inspect_auto_reload_blockers",
    "_handle_dev_mode_reload_trigger",
    "_parse_bool_flag",
    "_require_explicit_overwrite_confirmation",
    "_build_dirty_overwrite_detail",
    "_control_plane_install_base_url",
    "_require_control_plane_install",
    "_set_validation_followup_result",
    "_should_run_restart_webhook",
    "_defer_restart_webhook_if_blocked",
    "_sync_install_time_registries",
    "_schedule_pack_validation_on_current_loop",
    "run_install_pipeline",
    "install_from_file",
    "install_from_cloud",
]
