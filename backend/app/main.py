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
    from backend.app.services.system_health_checker import SystemHealthChecker

    health_checker = SystemHealthChecker()

    # Perform basic system checks (without workspace requirement)
    issues = []

    # Check LLM configuration
    llm_status = await health_checker._check_llm_configuration("default-user", issues)

    # Check Vector DB connection
    vector_db_status = await health_checker._check_vector_db(issues)

    # Check backend service
    backend_status = await health_checker._check_backend_service(issues)

    # Check OCR service
    ocr_status = await health_checker._check_ocr_service(issues)

    # Determine overall status
    overall_status = "healthy"
    if any(i.severity == "error" for i in issues):
        overall_status = "unhealthy"
    elif any(i.severity == "warning" for i in issues):
        overall_status = "degraded"

    return {
        "status": overall_status,
        "service": "my-agent-mindscape-backend",
        "version": "1.0.0",
        "components": {
            "backend": backend_status.get("status", "unknown"),
            "llm_configured": llm_status.get("configured", False),
            "llm_available": llm_status.get("available", False),
            "vector_db_connected": vector_db_status.get("connected", False),
            "ocr_service": ocr_status.get("status", "unknown"),
        },
        "llm_configured": llm_status.get("configured", False),
        "llm_available": llm_status.get("available", False),
        "llm_provider": llm_status.get("provider"),
        "vector_db_connected": vector_db_status.get("connected", False),
        "ocr_service": ocr_status,
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

    logger.info(f"Starting My Agent Console API on {host}:{port}")

    uvicorn.run(
        "backend.app.main:app",
        host=host,
        port=port,
        workers=workers,
        reload=os.getenv("ENVIRONMENT") == "development",
        log_level="info",
    )


if __name__ == "__main__":
    main()
