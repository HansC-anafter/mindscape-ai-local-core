import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException

from backend.app.core.backend_runtime_mode import (
    is_execution_plane,
    should_allow_implicit_pack_reload,
)

logger = logging.getLogger(__name__)
OVERWRITE_CONFIRMATION_PHRASE = "OVERWRITE"
OVERWRITE_REVIEW_CONFIRMATION_PHRASE = "REVIEWED_LOCAL_DIFFS"
_configured_temp_dir: Optional[Path] = None


def _utc_now():
    """Return timezone-aware UTC now."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


# ------------------------------------------------------------------
# Resolve local-core root (shared helper)
# ------------------------------------------------------------------


def _resolve_local_core_root() -> Path:
    """Resolve workspace root from current file location."""
    return Path(__file__).resolve().parents[5]


def _ensure_sys_path():
    """Add backend dir to sys.path if needed."""
    import sys

    backend_dir = str(Path(__file__).resolve().parents[3])
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


def _resolve_runtime_temp_dir() -> Path:
    """Pick a writable temp dir even when system temp paths are unavailable."""
    global _configured_temp_dir
    if _configured_temp_dir is not None:
        return _configured_temp_dir

    local_core_root = _resolve_local_core_root()
    candidates = [
        Path(os.getenv("MINDSCAPE_RUNTIME_TMPDIR", "")).expanduser()
        if os.getenv("MINDSCAPE_RUNTIME_TMPDIR")
        else None,
        local_core_root / "backend" / ".tmp",
        Path("/app/backend/.tmp"),
        Path("/app/.tmp"),
    ]

    for candidate in candidates:
        if candidate is None:
            continue
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe_path = candidate / ".tmp_write_probe"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink()
            resolved = candidate.resolve()
            tempfile.tempdir = str(resolved)
            os.environ["TMPDIR"] = str(resolved)
            os.environ["TEMP"] = str(resolved)
            os.environ["TMP"] = str(resolved)
            _configured_temp_dir = resolved
            logger.info("Configured capability install temp dir: %s", resolved)
            return resolved
        except Exception as exc:
            logger.warning(
                "Temp dir candidate unusable for capability install: %s (%s)",
                candidate,
                exc,
            )

    raise RuntimeError("No writable temp directory available for capability install")


try:
    _resolve_runtime_temp_dir()
except Exception as exc:
    logger.warning("Failed to preconfigure capability install temp dir: %s", exc)


def _supports_file_touch_reload() -> bool:
    """
    Detect whether touching a watched file can actually restart backend.

    We only auto-report restart_triggered=true when uvicorn is running with --reload.
    """
    for proc_cmdline in ("/proc/1/cmdline", "/proc/self/cmdline"):
        try:
            raw = Path(proc_cmdline).read_bytes()
            if b"--reload" in raw:
                return True
        except Exception:
            continue
    return False


def _inspect_auto_reload_blockers() -> Dict[str, Any]:
    """Return whether auto reload should be deferred to avoid killing active work."""
    return inspect_restart_blockers()


def _handle_dev_mode_reload_trigger(
    *,
    pipeline,
    result,
    capability_code: str,
    env: str,
    trigger_path: Optional[Path] = None,
) -> None:
    if env not in ("development", "dev"):
        return
    if not should_allow_implicit_pack_reload(environment=env):
        if is_execution_plane():
            result.add_warning(
                f"Deferred backend auto-reload for {capability_code}: execution-plane backend does not allow implicit pack reloads."
            )
            logger.info(
                "Deferred auto reload for %s because backend is running in execution-plane mode",
                capability_code,
            )
        else:
            result.add_warning(
                f"Deferred backend auto-reload for {capability_code}: implicit pack reloads are disabled by configuration."
            )
            logger.info(
                "Deferred auto reload for %s because implicit pack reloads are disabled",
                capability_code,
            )
        return
    blockers = _inspect_auto_reload_blockers()
    if blockers.get("blocked"):
        if blockers.get("reason") == "active_workloads":
            fragments = []
            for key, label in (
                ("active_compile_jobs", "compile_jobs"),
                ("active_meeting_sessions", "meeting_sessions"),
                ("active_pending_dispatch", "pending_dispatch"),
            ):
                count = blockers.get(key)
                if isinstance(count, int) and count > 0:
                    fragments.append(f"{label}={count}")
            detail = ", ".join(fragments) or "unknown workload counts"
            result.add_warning(
                f"Deferred backend auto-reload for {capability_code}: active workloads are still running ({detail})."
            )
            logger.info(
                "Deferred auto reload for %s because active workloads are present: %s",
                capability_code,
                detail,
            )
        else:
            result.add_warning(
                f"Deferred backend auto-reload for {capability_code}: could not safely inspect active workloads."
            )
            logger.info(
                "Deferred auto reload for %s because workload inspection failed",
                capability_code,
            )
        return
    if _supports_file_touch_reload():
        try:
            trigger = trigger_path or Path("/app/backend/app/capabilities/.reload_trigger")
            trigger.touch()
            pipeline.restart_triggered = True
            pipeline.restart_required = False
            logger.info(f"Reload triggered for {capability_code} via file touch")
        except Exception as exc:
            logger.warning(f"Failed to trigger reload: {exc}")
            result.add_warning(f"Restart required - auto-trigger failed: {exc}")
    else:
        result.add_warning(
            "Backend is not running with --reload; auto file-touch restart skipped."
        )
        logger.info(
            "Auto file-touch restart skipped for %s: --reload not detected",
            capability_code,
        )


def _parse_bool_flag(value: str) -> bool:
    return str(value or "").strip().lower() in ("true", "1", "yes")


def _require_explicit_overwrite_confirmation(
    *,
    allow_overwrite: bool,
    overwrite_confirmation: str,
) -> None:
    if not allow_overwrite:
        return

    if str(overwrite_confirmation or "").strip() == OVERWRITE_CONFIRMATION_PHRASE:
        return

    raise HTTPException(
        status_code=409,
        detail={
            "error": "overwrite_confirmation_required",
            "message": "Overwrite install requires explicit confirmation.",
            "required_confirmation": OVERWRITE_CONFIRMATION_PHRASE,
            "hint": (
                "Resubmit with allow_overwrite=true and "
                f"overwrite_confirmation={OVERWRITE_CONFIRMATION_PHRASE}"
            ),
        },
    )


def _build_dirty_overwrite_detail(
    *,
    dirty,
    incoming_version: Optional[str],
    review_payload: Optional[Dict[str, Any]],
    error: str,
    message: str,
    hint: str,
) -> Dict[str, Any]:
    detail: Dict[str, Any] = {
        "error": error,
        "message": message,
        "installed_version": dirty.installed_version,
        "installed_at": dirty.installed_at,
        "incoming_version": incoming_version,
        "modified": dirty.modified,
        "added": dirty.added,
        "deleted": dirty.deleted,
        "summary": dirty.summary(),
        "required_confirmation": OVERWRITE_CONFIRMATION_PHRASE,
        "required_review_confirmation": OVERWRITE_REVIEW_CONFIRMATION_PHRASE,
        "review_required": True,
        "review_summary": (
            "Review each conflict against the incoming pack before force overwrite. "
            "If any local-core fix is missing from cloud source, reconcile source first."
        ),
        "hint": hint,
    }
    if review_payload is not None:
        detail["review"] = review_payload
    return detail


def _control_plane_install_base_url() -> str:
    host = os.getenv("MINDSCAPE_CONTROL_PLANE_HOST", "localhost")
    port = os.getenv("MINDSCAPE_CONTROL_PLANE_HOST_PORT", "8220")
    return f"http://{host}:{port}"


def _require_control_plane_install(route_name: str) -> None:
    if not is_execution_plane():
        return

    base_url = _control_plane_install_base_url()
    raise HTTPException(
        status_code=409,
        detail={
            "error": "install_requires_control_plane",
            "message": (
                f"{route_name} is disabled on execution-plane backends because "
                "self-install can complete the filesystem mutation but leave the "
                "HTTP response hanging."
            ),
            "backend_role": "execution",
            "required_plane": "control",
            "control_plane_base_url": base_url,
            "hint": (
                "Send capability pack install requests to the backend-control "
                f"service instead, for example {base_url}/api/v1/capability-packs/install-from-file"
            ),
        },
    )


# ------------------------------------------------------------------
# Shared install pipeline
# ------------------------------------------------------------------
