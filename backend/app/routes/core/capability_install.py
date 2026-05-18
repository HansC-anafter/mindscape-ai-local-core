"""
Capability Install Routes compatibility entrypoint.
"""

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

__all__ = [
    "router",
    "OVERWRITE_CONFIRMATION_PHRASE",
    "OVERWRITE_REVIEW_CONFIRMATION_PHRASE",
    "InstallPipelineResult",
    "InstallRegistrySyncState",
    "InstallFromCloudRequest",
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
