"""
System control endpoints (restart, health check, etc.)
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Dict, Any
import os
import logging

from app.services.restart_webhook import get_restart_webhook_service

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_SERVICES = {"backend", "runner", "all"}
_LOCALHOST_ADDRS = {"127.0.0.1", "localhost", "::1", "unknown"}


class RestartRequest(BaseModel):
    service: str = Field(default="backend")


def _build_manual_instruction(targets: list[str]) -> str:
    return f"docker compose restart {' '.join(targets)}"


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


@router.post("/restart", response_model=Dict[str, Any])
async def restart_service(request: Request, body: RestartRequest = RestartRequest()):
    """
    Restart local-core services through Device Node webhook.

    Supported services:
    - backend
    - runner
    - all (backend + runner)
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

        targets = ["backend", "runner"] if service == "all" else [service]
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
