"""
My Agent Console - Backend API
FastAPI application for personal AI agent platform
"""

import os
import signal
import faulthandler
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import logging
import uvicorn

from backend.app.core.backend_runtime_mode import (
    get_backend_runtime_role,
    should_enable_uvicorn_reload,
)
from backend.app.core.security import security_monitor
from backend.app.app_bootstrap.cors import get_cors_origins, get_cors_origin_regex
from backend.app.app_bootstrap.routes import register_all_routes
from backend.app.app_bootstrap.lifecycle import lifespan
from backend.app.app_bootstrap.error_handlers import register_error_handlers

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def _enable_usr1_faulthandler():
    if not (os.getenv("PYTHONFAULTHANDLER") or os.getenv("ENABLE_FAULTHANDLER")):
        return
    try:
        faulthandler.enable()
        faulthandler.register(signal.SIGUSR1, all_threads=True)
        faulthandler.register(signal.SIGUSR2, all_threads=True)
        logger.info("Faulthandler enabled: SIGUSR1/SIGUSR2 will dump stack traces.")
    except Exception:
        logger.exception("Failed to enable faulthandler.")

_enable_usr1_faulthandler()

# Create FastAPI app
app = FastAPI(
    title="My Agent Console API",
    description="Personal AI agent platform with mindscape management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware - MUST be first middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_origin_regex=get_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Trusted host middleware - AFTER CORS
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "localhost",
        "127.0.0.1",
        "host.docker.internal",
        "*",
    ],  # Allow all for development
)


@app.get("/healthz")
async def healthz():
    """Pure liveness probe for the API process.

    This endpoint must stay dependency-free: no OCR, LLM, vector DB, object index,
    workspace health, or external service checks. Readiness/system health belongs
    to /health and /api/v1/workspaces/{workspace_id}/health.
    """
    return {
        "status": "ok",
        "backend_role": get_backend_runtime_role(),
        "reload_enabled": should_enable_uvicorn_reload(),
    }


# Connect modular bootstrap components
register_all_routes(app)
register_error_handlers(app)


if os.getenv("PYTHONFAULTHANDLER") or os.getenv("ENABLE_FAULTHANDLER"):

    @app.post("/debug/dump-stacks")
    async def _dump_stacks():
        faulthandler.dump_traceback(all_threads=True)
        return {"ok": True}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to My Agent Console API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.post("/api/v1/admin/reset-rate-limit")
async def reset_rate_limit(request: Request):
    """Reset rate limit for development (only allows localhost)"""
    client_ip = request.client.host if request.client else "unknown"

    # Only allow localhost for security
    if client_ip not in ["127.0.0.1", "localhost", "::1", "unknown"]:
        # Check if it's from docker internal network (common in dev)
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if "127.0.0.1" not in forwarded_for and "localhost" not in forwarded_for:
            raise HTTPException(
                status_code=403, detail="Only localhost can reset rate limits"
            )

    security_monitor.reset_rate_limit()
    return {"status": "ok", "message": "Rate limits cleared"}


@app.get("/health")
async def health_check():
    """Overall health check with system component status"""
    from backend.app.services.system_health_checker import (
        SystemHealthChecker,
        run_readiness_coro_in_worker,
    )

    health_checker = SystemHealthChecker()

    # Perform basic system checks (without workspace requirement)
    issues = []

    # Check LLM configuration
    llm_status = await run_readiness_coro_in_worker(
        lambda: health_checker._check_llm_configuration("default-user", issues)
    )

    # Check Vector DB connection
    vector_db_status = await run_readiness_coro_in_worker(
        lambda: health_checker._check_vector_db(issues)
    )

    # Check backend service
    backend_status = await run_readiness_coro_in_worker(
        lambda: health_checker._check_backend_service(issues)
    )

    # Check OCR service
    ocr_status = await run_readiness_coro_in_worker(
        lambda: health_checker._check_ocr_service(issues)
    )

    # Determine overall status
    overall_status = "healthy"
    if any(i.severity == "error" for i in issues):
        overall_status = "unhealthy"
    elif any(i.severity == "warning" for i in issues):
        overall_status = "degraded"

    backend_role = get_backend_runtime_role()
    reload_enabled = should_enable_uvicorn_reload()
    runtime_migrations_post_ready_status = getattr(
        app.state,
        "runtime_migrations_post_ready_status",
        "unknown",
    )
    runtime_migrations_post_ready_error = getattr(
        app.state,
        "runtime_migrations_post_ready_error",
        None,
    )
    playbook_registry_post_ready_status = getattr(
        app.state,
        "playbook_registry_post_ready_status",
        "unknown",
    )
    playbook_registry_post_ready_error = getattr(
        app.state,
        "playbook_registry_post_ready_error",
        None,
    )
    tool_rag_post_ready_status = getattr(
        app.state,
        "tool_rag_post_ready_status",
        "unknown",
    )
    tool_rag_post_ready_error = getattr(
        app.state,
        "tool_rag_post_ready_error",
        None,
    )
    object_index_sync_status = getattr(
        app.state,
        "object_index_sync_status",
        "unknown",
    )
    object_index_sync_error = getattr(
        app.state,
        "object_index_sync_error",
        None,
    )
    try:
        from backend.app.services.object_index_sync_service import (
            get_object_index_sync_status,
        )

        object_index_sync_snapshot = get_object_index_sync_status().snapshot()
        object_index_sync_snapshot.pop("workspaces", None)
    except Exception as exc:
        object_index_sync_snapshot = {"state": "unavailable", "error": str(exc)}

    return {
        "status": overall_status,
        "service": "my-agent-mindscape-backend",
        "version": "1.0.0",
        "backend_role": backend_role,
        "uvicorn_reload_enabled": reload_enabled,
        "components": {
            "backend": backend_status.get("status", "unknown"),
            "llm_configured": llm_status.get("configured", False),
            "llm_available": llm_status.get("available", False),
            "vector_db_connected": vector_db_status.get("connected", False),
            "ocr_service": ocr_status.get("status", "unknown"),
            "post_ready_playbook_registry": playbook_registry_post_ready_status,
            "post_ready_runtime_migrations": runtime_migrations_post_ready_status,
            "tool_rag_post_ready": tool_rag_post_ready_status,
            "object_index_sync": object_index_sync_status,
        },
        "llm_configured": llm_status.get("configured", False),
        "llm_available": llm_status.get("available", False),
        "llm_provider": llm_status.get("provider"),
        "vector_db_connected": vector_db_status.get("connected", False),
        "ocr_service": ocr_status,
        "post_ready_playbook_registry": {
            "status": playbook_registry_post_ready_status,
            "error": playbook_registry_post_ready_error,
        },
        "post_ready_runtime_migrations": {
            "status": runtime_migrations_post_ready_status,
            "error": runtime_migrations_post_ready_error,
        },
        "tool_rag_post_ready": {
            "status": tool_rag_post_ready_status,
            "error": tool_rag_post_ready_error,
        },
        "object_index_sync": {
            "status": object_index_sync_status,
            "error": object_index_sync_error,
            "snapshot": object_index_sync_snapshot,
        },
        "issues": [issue.to_dict() for issue in issues] if issues else [],
    }


# Service URLs reachable from inside Docker (backend proxies these for the frontend)
_HOST_SERVICE_URLS: dict = {
    "xtts": os.getenv("XTTS_SERVICE_URL", "http://xtts-service:8020") + "/health",
    "mcp-gateway": os.getenv(
        "MCP_GATEWAY_HEALTH_URL", "http://host.docker.internal:8180/health"
    ),
}


@app.get("/api/v1/host/services/{service}/health")
async def host_service_health(service: str):
    """
    Proxy health checks for host/sidecar services that the frontend cannot reach directly.

    Supported services:
      - xtts         → xtts-service:8020/health  (Docker sidecar)
      - mcp-gateway  → host.docker.internal:8180/health (Node process on host)
    """
    import httpx as _httpx

    url = _HOST_SERVICE_URLS.get(service)
    if not url:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service}")

    try:
        async with _httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url)
            return r.json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


# Debug endpoint to list all registered routes
@app.get("/debug/routes")
async def debug_list_routes():
    """Temporary debug endpoint to list all registered routes"""
    routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            routes.append(
                {
                    "path": route.path,
                    "methods": list(route.methods) if route.methods else [],
                    "name": route.name if hasattr(route, "name") else None,
                }
            )
    # Filter to show only mindscape routes
    mindscape_routes = [r for r in routes if "mindscape" in r["path"].lower()]
    return {
        "total_routes": len(routes),
        "mindscape_routes": mindscape_routes,
        "sample_routes": routes[:20],
    }


def main():
    """Main entry point for running the server"""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("WORKERS", "1"))
    reload_enabled = should_enable_uvicorn_reload()

    logger.info(
        "Starting My Agent Console API on %s:%s (reload=%s)",
        host,
        port,
        reload_enabled,
    )

    uvicorn.run(
        "backend.app.main:app",
        host=host,
        port=port,
        workers=workers,
        reload=reload_enabled,
        log_level="info",
    )


if __name__ == "__main__":
    main()
