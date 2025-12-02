"""
My Agent Console - Backend API
FastAPI application for personal AI agent platform
"""

import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
import uvicorn

# Layer 0: Kernel Routes (must be hardcoded)
from .routes.core import (
    workspace,
    playbook,
    playbook_execution,
    config,
    system_settings,
    tools,
    tool_connections,
)

# Layer 1: Core Primitives (manager hardcoded, content pluggable)
from .routes.core import (
    vector_db,
    vector_search,
    capability_packs,
)

# Layer 2: Feature routes loaded via pack registry
from .core.pack_registry import load_and_register_packs
from .core.security import security_monitor, auth_manager
from .init_db import init_mindscape_tables
from .capabilities.registry import load_capabilities

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="My Agent Console API",
    description="Personal AI agent platform with mindscape management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware - MUST be first middleware (before TrustedHostMiddleware)
# This ensures CORS headers are added to all responses, including error responses
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Trusted host middleware - AFTER CORS
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "host.docker.internal", "*"]  # Allow all for development
)

# Phase 1: Register Layer 0 kernel routes
def register_core_routes(app: FastAPI) -> None:
    """Register Layer 0 kernel routes"""
    app.include_router(workspace.router, tags=["workspace"])
    app.include_router(playbook.router, tags=["playbook"])
    app.include_router(playbook_execution.router, tags=["playbook"])
    app.include_router(config.router, tags=["config"])
    app.include_router(system_settings.router, tags=["system"])
    app.include_router(tools.router, tags=["tools"])
    app.include_router(tool_connections.router, tags=["tools"])

# Phase 2: Register Layer 1 core primitives
def register_core_primitives(app: FastAPI) -> None:
    """Register Layer 1 core primitives (manager hardcoded, content pluggable)"""
    app.include_router(vector_db.router, tags=["vector-db"])
    app.include_router(vector_search.router, tags=["vector-search"])
    app.include_router(capability_packs.router, tags=["capability-packs"])

# Phase 1: Register Layer 0 kernel routes
register_core_routes(app)

# Phase 2: Register Layer 1 core primitives
register_core_primitives(app)

# Phase 3: Register Layer 2 feature routes via pack registry
# Note: Pack loading failures are logged but do not prevent app startup (loose coupling)
try:
    load_and_register_packs(app)
except Exception as e:
    logger.warning(f"Failed to load some feature packs during startup: {e}. App will continue to start.")
    # Continue startup - core functionality should still work


@app.on_event("startup")
async def startup_event():
    """Initialize database tables and background tasks on startup"""
    logger.info("Initializing mindscape database tables...")
    try:
        init_mindscape_tables()
        logger.info("Mindscape tables initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize mindscape tables (will retry on first use): {e}")

    # Load capability packages
    logger.info("Loading capability packages...")
    try:
        from pathlib import Path
        app_dir = Path(__file__).parent
        capabilities_dir = app_dir / "capabilities"
        load_capabilities(capabilities_dir)
        logger.info("Capability packages loaded successfully")
    except Exception as e:
        logger.warning(f"Failed to load capability packages: {e}", exc_info=True)

    # Start habit proposal worker (periodic task)
    try:
        from .capabilities.habit_learning.services.habit_proposal_worker import HabitProposalWorker
        import asyncio

        # Get interval (hours), default 1 hour
        interval_hours = int(os.getenv("HABIT_PROPOSAL_INTERVAL_HOURS", "1"))

        worker = HabitProposalWorker()
        # Run periodic task in background
        asyncio.create_task(worker.run_periodic_task(interval_hours=interval_hours))
        logger.info(f"Habit proposal worker started (interval: {interval_hours} hours)")
    except Exception as e:
        logger.warning(f"Failed to start habit proposal worker: {e}")
        # Don't affect app startup, continue running


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to My Agent Console API",
        "version": "1.0.0",
        "docs": "/docs"
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
            raise HTTPException(status_code=403, detail="Only localhost can reset rate limits")

    security_monitor.reset_rate_limit()
    return {"status": "ok", "message": "Rate limits cleared"}

@app.get("/health")
async def health_check():
    """Overall health check with system component status"""
    from .services.system_health_checker import SystemHealthChecker

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
        "issues": [issue.to_dict() for issue in issues] if issues else []
    }


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Security monitoring middleware"""
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting check
    if security_monitor.check_rate_limit(client_ip):
        retry_after = security_monitor.rate_limit_window * 60
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={
                "Retry-After": str(retry_after),
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
                "Access-Control-Allow-Headers": "*",
            }
        )

    # Log request details for file upload debugging
    if "/files/upload" in str(request.url.path):
        request_id = request.headers.get('x-request-id', f"req-{id(request)}")
        content_type = request.headers.get('content-type', 'N/A')
        content_length = request.headers.get('content-length', 'N/A')
        client_ip = request.client.host if request.client else "unknown"

        logger.info(f"[{request_id}] === MIDDLEWARE: FILE UPLOAD REQUEST START ===")
        logger.info(f"[{request_id}] Method: {request.method}")
        logger.info(f"[{request_id}] Path: {request.url.path}")
        logger.info(f"[{request_id}] Query params: {dict(request.query_params)}")
        logger.info(f"[{request_id}] Client IP: {client_ip}")
        logger.info(f"[{request_id}] Content-Type: {content_type}")
        logger.info(f"[{request_id}] Content-Length: {content_length}")
        logger.info(f"[{request_id}] All headers: {dict(request.headers)}")

        import sys
        sys.stderr.write(f"[{request_id}] MIDDLEWARE: File upload request detected\n")
        sys.stderr.write(f"[{request_id}] Path: {request.url.path}\n")
        sys.stderr.write(f"[{request_id}] Content-Type: {content_type}\n")
        sys.stderr.flush()

    try:
        request_id = request.headers.get('x-request-id', f"req-{id(request)}") if "/files/upload" in str(request.url.path) else None
        response = await call_next(request)
        if "/files/upload" in str(request.url.path) and request_id:
            logger.info(f"[{request_id}] === MIDDLEWARE: RESPONSE ====")
            logger.info(f"[{request_id}] Status code: {response.status_code}")
            logger.info(f"[{request_id}] Response headers: {dict(response.headers)}")
            if response.status_code == 422:
                logger.error(f"[{request_id}] 422 ERROR in middleware")
                import sys
                sys.stderr.write(f"[{request_id}] MIDDLEWARE: 422 error detected\n")
                sys.stderr.flush()
        return response
    except RequestValidationError as e:
        if "/files/upload" in str(request.url.path):
            request_id = request.headers.get('x-request-id', f"req-{id(request)}")
            logger.error(f"[{request_id}] === MIDDLEWARE: RequestValidationError ===")
            logger.error(f"[{request_id}] Errors: {e.errors()}", exc_info=True)
            import sys
            sys.stderr.write(f"[{request_id}] MIDDLEWARE: RequestValidationError\n")
            sys.stderr.write(f"[{request_id}] Errors: {e.errors()}\n")
            sys.stderr.flush()
        raise
    except Exception as e:
        if "/files/upload" in str(request.url.path):
            request_id = request.headers.get('x-request-id', f"req-{id(request)}")
            logger.error(f"[{request_id}] === MIDDLEWARE: Exception ===")
            logger.error(f"[{request_id}] Exception: {str(e)}", exc_info=True)
            import sys
            sys.stderr.write(f"[{request_id}] MIDDLEWARE: Exception: {str(e)}\n")
            sys.stderr.flush()
        raise


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors (422) with detailed logging"""
    request_id = request.headers.get('x-request-id', f"req-{id(request)}")
    error_details = exc.errors()
    import json
    import sys

    logger.error(f"[{request_id}] === EXCEPTION HANDLER: RequestValidationError ===")
    logger.error(f"[{request_id}] Method: {request.method}")
    logger.error(f"[{request_id}] Path: {request.url.path}")
    logger.error(f"[{request_id}] Query params: {dict(request.query_params)}")

    # Log to both logger and stderr for maximum visibility
    error_json = json.dumps(error_details, indent=2, ensure_ascii=False)
    logger.error(f"[{request_id}] Error details: {error_json}")
    logger.error(f"[{request_id}] Request headers: {dict(request.headers)}")

    # Force output to stderr (will be captured by docker logs)
    error_msg = f"[{request_id}] VALIDATION ERROR: {request.method} {request.url.path}\n"
    error_msg += f"[{request_id}] Errors: {error_json}\n"
    error_msg += f"[{request_id}] Headers: {dict(request.headers)}\n"
    sys.stderr.write(error_msg)
    sys.stderr.flush()

    # Try to get request body for debugging (if available)
    try:
        if hasattr(request, '_body'):
            body_preview = str(request._body)[:500] if request._body else "None"
            logger.error(f"[{request_id}] Request body (first 500 chars): {body_preview}")
            sys.stderr.write(f"[{request_id}] Request body preview: {body_preview}\n")
            sys.stderr.flush()
    except Exception as e:
        logger.error(f"[{request_id}] Could not read request body: {e}")

    logger.error(f"[{request_id}] === EXCEPTION HANDLER: Returning 422 response ===")
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=422,
        content={"detail": error_details},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "*",
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with CORS headers"""
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "*",
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with CORS headers"""
    import traceback
    import sys
    exc_type, exc_value, exc_tb = exc.__class__, exc, exc.__traceback__
    full_traceback = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.error(f"Unhandled exception: {str(exc)}\n{full_traceback}")
    # Also print to stderr for immediate visibility
    print(f"ERROR: Unhandled exception: {str(exc)}", file=sys.stderr)
    print(full_traceback, file=sys.stderr)
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )


def main():
    """Main entry point for running the server"""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("WORKERS", "1"))

    logger.info(f"Starting My Agent Console API on {host}:{port}")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=workers,
        reload=os.getenv("ENVIRONMENT") == "development",
        log_level="info"
    )


if __name__ == "__main__":
    main()
