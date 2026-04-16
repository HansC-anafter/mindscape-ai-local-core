"""
System control endpoints (restart, health check, etc.)
"""

import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Dict, Any
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
import logging

try:
    from backend.app.services.restart_webhook import get_restart_webhook_service
except ImportError:
    from app.services.restart_webhook import get_restart_webhook_service

router = APIRouter()
logger = logging.getLogger(__name__)

_RUNNER_SENTINEL_PATH = Path("/app/data/.restart_runner")
_RUNNER_SENTINEL_TTL_SECONDS = 300
_RUNNER_DRAIN_SENTINEL_PATH = Path("/app/data/.drain_runner")
_RUNNER_DRAIN_TTL_SECONDS = 4 * 60 * 60

RUNNER_POOL_SERVICES = (
    "runner-default",
    "runner-browser",
    "runner-vision",
)
ALLOWED_SERVICES = {"backend", "runner", "all", *RUNNER_POOL_SERVICES}
_LOCALHOST_ADDRS = {"127.0.0.1", "localhost", "::1", "unknown"}


class RestartRequest(BaseModel):
    service: str = Field(default="backend")


class RunnerDrainRequest(BaseModel):
    enabled: bool = Field(default=True)
    ttl_seconds: int = Field(default=_RUNNER_DRAIN_TTL_SECONDS, ge=30, le=86400)


def _build_manual_instruction(targets: list[str]) -> str:
    return f"docker compose restart {' '.join(targets)}"


def _expand_service_targets(service: str) -> list[str]:
    if service == "all":
        return ["backend", *RUNNER_POOL_SERVICES]
    if service == "runner":
        return list(RUNNER_POOL_SERVICES)
    return [service]


def _build_runner_drain_sentinel(ttl_seconds: int) -> Dict[str, Any]:
    return {
        "request_id": uuid.uuid4().hex,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": ttl_seconds,
        "mode": "drain",
    }


def _is_localhost(request: Request) -> bool:
    """Check if request originates from localhost or Docker internal network.

    Same pattern as admin/reset-rate-limit (main.py:L820-829), extended
    to also accept Docker bridge IPs (172.x.x.x) since host→container
    requests arrive via the Docker bridge network.
    """
    client_ip = request.client.host if request.client else "unknown"
    if client_ip in _LOCALHOST_ADDRS:
        return True
    # Docker bridge network (host → container comes as 172.x.x.x)
    if client_ip.startswith("172."):
        return True
    # Reverse proxy — check x-forwarded-for
    forwarded_for = request.headers.get("x-forwarded-for", "")
    return "127.0.0.1" in forwarded_for or "localhost" in forwarded_for


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _list_value(value: Any) -> list[Any]:
    return list(value or [])


def _env_int(name: str, default: int) -> int:
    try:
        return max(int(os.getenv(name, str(default)) or default), 0)
    except (TypeError, ValueError):
        return default


def _build_scene_generation_attention_reason(
    *,
    code: str,
    severity: str,
    message: str,
) -> Dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
    }


def _assess_scene_generation_dispatch_health(
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    if not summary.get("enabled"):
        summary["status"] = "disabled"
        summary["attention_reasons"] = []
        summary["recommended_actions"] = []
        return summary

    runnable_warn_threshold = _env_int(
        "SCENE_GENERATION_HEALTH_RUNNABLE_WARN_THRESHOLD",
        5,
    )
    deferred_warn_threshold = _env_int(
        "SCENE_GENERATION_HEALTH_DEFERRED_WARN_THRESHOLD",
        10,
    )
    cooldown_blocked_warn_threshold = _env_int(
        "SCENE_GENERATION_HEALTH_COOLDOWN_BLOCKED_WARN_THRESHOLD",
        1,
    )

    reasons: list[Dict[str, str]] = []
    actions: list[str] = []
    running = bool(summary.get("running"))
    pending_total = _int_value(summary.get("pending_total"))
    runnable_total = _int_value(summary.get("runnable_total"))
    deferred_total = _int_value(summary.get("deferred_total"))
    cooldown_blocked_total = _int_value(
        summary.get("provider_cooldown_blocked_total")
    )
    schema_ready = bool(summary.get("schema_ready", True))
    schema_table_name = str(
        summary.get("schema_table_name") or "scene_generation_jobs"
    )

    if not schema_ready:
        reasons.append(
            _build_scene_generation_attention_reason(
                code="dispatch_schema_missing",
                severity="warning",
                message=(
                    f"Scene generation dispatch schema is unavailable ({schema_table_name})."
                ),
            )
        )
        actions.append(
            "Run performance_direction scene generation migrations or disable the pack until the schema is installed."
        )

    if not running and pending_total > 0:
        reasons.append(
            _build_scene_generation_attention_reason(
                code="dispatch_not_running_with_pending_jobs",
                severity="error",
                message=(
                    "Scene generation dispatch is not running while pending jobs exist."
                ),
            )
        )
        actions.append(
            "Restart local-core backend or verify performance_direction background services started successfully."
        )

    if runnable_total >= max(runnable_warn_threshold, 1):
        reasons.append(
            _build_scene_generation_attention_reason(
                code="runnable_backlog_high",
                severity="warning" if running else "error",
                message=(
                    f"Runnable scene generation backlog reached {runnable_total} jobs."
                ),
            )
        )
        actions.append(
            "Inspect provider latency and dispatcher throughput for scene generation jobs."
        )

    if cooldown_blocked_total >= max(cooldown_blocked_warn_threshold, 1):
        reasons.append(
            _build_scene_generation_attention_reason(
                code="provider_cooldown_blocking_jobs",
                severity="warning",
                message=(
                    f"{cooldown_blocked_total} scene generation jobs are blocked by provider cooldown."
                ),
            )
        )
        actions.append(
            "Check scene generation provider credentials/configuration and clear cooldown after the provider is ready."
        )

    if deferred_total >= max(deferred_warn_threshold, 1):
        reasons.append(
            _build_scene_generation_attention_reason(
                code="deferred_retry_backlog_high",
                severity="warning",
                message=(
                    f"Deferred retry backlog reached {deferred_total} scene generation jobs."
                ),
            )
        )
        actions.append(
            "Inspect retry schedule and last_error fields for deferred scene generation jobs."
        )

    status = "healthy"
    if any(reason["severity"] == "error" for reason in reasons):
        status = "error"
    elif any(reason["severity"] == "warning" for reason in reasons):
        status = "warning"

    summary["status"] = status
    summary["attention_reasons"] = reasons
    summary["recommended_actions"] = list(dict.fromkeys(actions))
    summary["thresholds"] = {
        "runnable_warn_threshold": runnable_warn_threshold,
        "deferred_warn_threshold": deferred_warn_threshold,
        "cooldown_blocked_warn_threshold": cooldown_blocked_warn_threshold,
    }
    return summary


def _summarize_scene_generation_dispatch_status(status: Dict[str, Any]) -> Dict[str, Any]:
    pending = dict(status.get("pending_jobs") or {})
    ready = dict(status.get("ready_pending") or {})
    runnable = dict(status.get("runnable_pending") or {})
    cooldown_blocked = dict(status.get("provider_cooldown_blocked_pending") or {})
    deferred = dict(status.get("deferred_pending") or {})
    summary = {
        "enabled": True,
        "running": bool(status.get("running")),
        "provider_cooldowns_active": _int_value(
            status.get("provider_cooldowns_active")
        ),
        "pending_total": _int_value(pending.get("total_pending")),
        "ready_total": _int_value(ready.get("total_pending")),
        "runnable_total": _int_value(runnable.get("total_pending")),
        "provider_cooldown_blocked_total": _int_value(
            cooldown_blocked.get("total_pending")
        ),
        "deferred_total": _int_value(deferred.get("total_pending")),
        "provider_cooldowns": _list_value(status.get("provider_cooldowns")),
        "runnable_samples": _list_value(runnable.get("samples")),
        "provider_cooldown_blocked_samples": _list_value(
            cooldown_blocked.get("samples")
        ),
        "deferred_samples": _list_value(deferred.get("samples")),
        "timestamp": status.get("timestamp"),
        "schema_ready": bool(status.get("schema_ready", True)),
        "schema_status": status.get("schema_status"),
        "schema_table_name": status.get("schema_table_name"),
    }
    return _assess_scene_generation_dispatch_health(summary)


async def _get_scene_generation_dispatch_health() -> Dict[str, Any]:
    try:
        try:
            from backend.app.services.stores.installed_packs_store import (
                InstalledPacksStore,
            )
        except ImportError:
            from app.services.stores.installed_packs_store import (
                InstalledPacksStore,
            )

        enabled_pack_ids = set(InstalledPacksStore().list_enabled_pack_ids())
        if "performance_direction" not in enabled_pack_ids:
            return {
                "enabled": False,
                "status": "disabled",
            }

        try:
            from backend.app.capabilities.performance_direction.services.scene_generation_dispatch_manager import (
                get_scene_generation_dispatch_manager,
            )
        except ImportError:
            from app.capabilities.performance_direction.services.scene_generation_dispatch_manager import (
                get_scene_generation_dispatch_manager,
            )

        status = await get_scene_generation_dispatch_manager().get_status(
            sample_limit=2
        )
        return _summarize_scene_generation_dispatch_status(status)
    except Exception as e:
        logger.warning(
            "Failed to collect scene generation dispatch health: %s",
            e,
            exc_info=True,
        )
        return {
            "enabled": True,
            "status": "error",
            "error": str(e),
        }


async def _get_runner_queue_metrics_payload() -> Dict[str, Any]:
    try:
        from backend.app.services.stores.redis.runner_queue_store import (
            RedisRunnerQueueStore,
        )
    except ImportError:
        from app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

    return await RedisRunnerQueueStore.get_all_queue_metrics()


async def _get_runner_heartbeat_projection() -> list[Dict[str, Any]]:
    try:
        from backend.app.services.stores.tasks_store import TasksStore
    except ImportError:
        from app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()
    return await asyncio.to_thread(
        tasks_store.list_runner_heartbeats,
        max_age_seconds=300,
        limit=20,
    )


@router.post("/restart", response_model=Dict[str, Any])
async def restart_service(request: Request, body: RestartRequest = RestartRequest()):
    """
    Restart local-core services through Device Node webhook.

    Supported services:
    - backend
    - runner (all runner pools)
    - runner-default
    - runner-browser
    - runner-vision
    - all (backend + all runner pools)
    """
    try:
        # Localhost-only guard (v3 FIX)
        if not _is_localhost(request):
            raise HTTPException(
                status_code=403,
                detail="Restart API is restricted to localhost",
            )

        service = (body.service or "backend").strip().lower()
        if service not in ALLOWED_SERVICES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid service: {service}. Allowed: {sorted(ALLOWED_SERVICES)}",
            )

        targets = _expand_service_targets(service)
        instruction = _build_manual_instruction(targets)

        webhook_service = get_restart_webhook_service()
        if not webhook_service.is_configured():
            return {
                "success": False,
                "message": "Device Node webhook is not configured. Use manual restart command.",
                "method": "manual",
                "targets": targets,
                "instruction": instruction,
            }

        results: Dict[str, Any] = {}
        sent_all = True

        for target in targets:
            result = await webhook_service.notify_restart_required(
                capability_code=f"system_control_{target}",
                validation_passed=True,
                version="1.0.0",
                service=target,
            )
            results[target] = result
            if not result.get("sent"):
                sent_all = False

        if sent_all:
            return {
                "success": True,
                "message": f"Restart request sent via Device Node: {', '.join(targets)}",
                "method": "device_node",
                "targets": targets,
                "results": results,
            }

        # Fallback: sentinel file for runner when Device Node is unreachable.
        # Runner polls this file and performs graceful self-restart.
        runner_sentinel_written = False
        if service in ("runner", "all"):
            runner_failures = [
                results.get(target) or {}
                for target in RUNNER_POOL_SERVICES
            ]
            if any(
                result.get("reason") in {
                    "device_node_unreachable",
                    "timeout",
                    "http_error",
                    "error",
                }
                for result in runner_failures
            ):
                try:
                    sentinel = {
                        "request_id": uuid.uuid4().hex,
                        "requested_at": datetime.now(timezone.utc).isoformat(),
                        "ttl_seconds": _RUNNER_SENTINEL_TTL_SECONDS,
                    }
                    _RUNNER_SENTINEL_PATH.write_text(
                        json.dumps(sentinel), encoding="utf-8"
                    )
                    runner_sentinel_written = True
                    logger.info(
                        "Restart sentinel written for runner: %s",
                        sentinel["request_id"],
                    )
                except Exception as sentinel_err:
                    logger.warning(
                        "Failed to write runner restart sentinel: %s",
                        sentinel_err,
                    )

        if runner_sentinel_written:
            return {
                "success": True,
                "message": "Runner restart requested via sentinel file",
                "method": "runner_sentinel",
                "targets": [t for t in targets if t in RUNNER_POOL_SERVICES],
                "results": results,
                "partial": service == "all",
            }

        return {
            "success": False,
            "message": "Device Node restart failed or unavailable. Use manual restart command.",
            "method": "manual",
            "targets": targets,
            "results": results,
            "instruction": instruction,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restart service: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to restart service: {str(e)}"
        )


@router.post("/runner-drain", response_model=Dict[str, Any])
async def set_runner_drain(
    request: Request,
    body: RunnerDrainRequest = RunnerDrainRequest(),
):
    """Enable or clear the runner drain sentinel.

    When enabled, runners keep servicing inflight work but stop dequeuing
    additional tasks until the sentinel is cleared or expires.
    """
    try:
        if not _is_localhost(request):
            raise HTTPException(
                status_code=403,
                detail="Runner drain API is restricted to localhost",
            )

        if body.enabled:
            sentinel = _build_runner_drain_sentinel(body.ttl_seconds)
            _RUNNER_DRAIN_SENTINEL_PATH.write_text(
                json.dumps(sentinel),
                encoding="utf-8",
            )
            logger.info(
                "Runner drain sentinel written: %s",
                sentinel["request_id"],
            )
            return {
                "success": True,
                "enabled": True,
                "method": "runner_drain_sentinel",
                "path": str(_RUNNER_DRAIN_SENTINEL_PATH),
                "sentinel": sentinel,
                "message": "Runner drain enabled; runners will stop dequeuing new tasks.",
            }

        _RUNNER_DRAIN_SENTINEL_PATH.unlink(missing_ok=True)
        logger.info("Runner drain sentinel cleared")
        return {
            "success": True,
            "enabled": False,
            "method": "runner_drain_sentinel",
            "path": str(_RUNNER_DRAIN_SENTINEL_PATH),
            "message": "Runner drain cleared; runners may resume dequeuing.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update runner drain sentinel: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update runner drain sentinel: {str(e)}",
        )


@router.get("/health", response_model=Dict[str, Any])
async def get_service_health():
    """Get service health status"""
    try:
        import psutil

        process = psutil.Process()

        return {
            "status": "healthy",
            "pid": process.pid,
            "uptime_seconds": int(
                (psutil.boot_time() - process.create_time())
                if hasattr(psutil, "boot_time")
                else 0
            ),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "is_docker": os.path.exists("/.dockerenv"),
        }
    except ImportError:
        # psutil not available, return basic info
        return {"status": "healthy", "is_docker": os.path.exists("/.dockerenv")}
    except Exception as e:
        logger.error(f"Failed to get health status: {e}", exc_info=True)
        return {"status": "unknown", "error": str(e)}

@router.get("/health/queue/metrics", response_model=Dict[str, Any])
async def get_queue_metrics():
    """Get queue metrics plus active runner and scene dispatch health."""
    try:
        metrics = await _get_runner_queue_metrics_payload()
        metrics["runners"] = await _get_runner_heartbeat_projection()
        metrics["scene_generation_dispatch"] = (
            await _get_scene_generation_dispatch_health()
        )
        return metrics
    except Exception as e:
        logger.error(f"Failed to get Redis queue metrics: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
