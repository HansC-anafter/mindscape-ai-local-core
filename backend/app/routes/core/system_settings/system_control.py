"""
System control endpoints (restart, health check, etc.)
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import os
import subprocess
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/restart", response_model=Dict[str, Any])
async def restart_service():
    """
    Restart the backend service

    Note: This endpoint attempts to restart the service.
    In Docker environments, this may require external orchestration.
    """
    try:
        # Check if we're in a Docker container
        is_docker = os.path.exists("/.dockerenv")

        if is_docker:
            # In Docker, we can't directly restart the container
            # But we can trigger a graceful shutdown, and Docker Compose will restart it
            # Or we can try to call docker compose from within the container (if available)

            # Try to find docker-compose command
            docker_compose_paths = [
                "/usr/local/bin/docker-compose",
                "/usr/bin/docker-compose",
                "docker-compose"
            ]

            docker_compose_cmd = None
            for path in docker_compose_paths:
                try:
                    result = subprocess.run(
                        ["which", path.split("/")[-1]],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0:
                        docker_compose_cmd = result.stdout.strip()
                        break
                except:
                    continue

            if docker_compose_cmd:
                # Try to restart via docker-compose
                # This requires the container to have access to docker socket
                try:
                    # Get project directory (assuming we're in /app)
                    project_dir = os.getenv("PROJECT_ROOT", "/app/..")
                    result = subprocess.run(
                        [docker_compose_cmd, "restart", "backend"],
                        cwd=project_dir,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        return {
                            "success": True,
                            "message": "Service restart initiated via docker-compose",
                            "method": "docker-compose"
                        }
                except Exception as e:
                    logger.warning(f"Failed to restart via docker-compose: {e}")

            # Fallback: Return instruction for manual restart
            return {
                "success": True,
                "message": "Service restart requested. Please run: docker compose restart backend",
                "method": "manual",
                "instruction": "docker compose restart backend"
            }
        else:
            # Not in Docker, try to restart via systemd or supervisor
            # This is more complex and environment-specific
            return {
                "success": False,
                "message": "Automatic restart not available in this environment",
                "method": "manual",
                "instruction": "Please restart the service manually"
            }

    except Exception as e:
        logger.error(f"Failed to restart service: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restart service: {str(e)}"
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
            "uptime_seconds": int((psutil.boot_time() - process.create_time()) if hasattr(psutil, 'boot_time') else 0),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "is_docker": os.path.exists("/.dockerenv")
        }
    except ImportError:
        # psutil not available, return basic info
        return {
            "status": "healthy",
            "is_docker": os.path.exists("/.dockerenv")
        }
    except Exception as e:
        logger.error(f"Failed to get health status: {e}", exc_info=True)
        return {
            "status": "unknown",
            "error": str(e)
        }

