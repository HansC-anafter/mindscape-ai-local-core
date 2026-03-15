from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import json
import sys
import traceback

from backend.app.core.security import security_monitor
from .cors import resolve_error_cors_origin

logger = logging.getLogger(__name__)

async def security_middleware(request: Request, call_next):
    """Security monitoring middleware"""
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting check
    if security_monitor.check_rate_limit(client_ip):
        retry_after = security_monitor.rate_limit_window * 60
        origin = resolve_error_cors_origin(request.headers.get("origin", "*"))
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={
                "Retry-After": str(retry_after),
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
                "Access-Control-Allow-Headers": "*",
            },
        )

    # Log request details for file upload debugging
    if "/files/upload" in str(request.url.path):
        request_id = request.headers.get("x-request-id", f"req-{id(request)}")
        content_type = request.headers.get("content-type", "N/A")
        content_length = request.headers.get("content-length", "N/A")
        
        logger.info(f"[{request_id}] === MIDDLEWARE: FILE UPLOAD REQUEST START ===")
        logger.info(f"[{request_id}] Method: {request.method}")
        logger.info(f"[{request_id}] Path: {request.url.path}")
        logger.info(f"[{request_id}] Query params: {dict(request.query_params)}")
        logger.info(f"[{request_id}] Client IP: {client_ip}")
        logger.info(f"[{request_id}] Content-Type: {content_type}")
        logger.info(f"[{request_id}] Content-Length: {content_length}")
        logger.info(f"[{request_id}] All headers: {dict(request.headers)}")

        sys.stderr.write(f"[{request_id}] MIDDLEWARE: File upload request detected\n")
        sys.stderr.write(f"[{request_id}] Path: {request.url.path}\n")
        sys.stderr.write(f"[{request_id}] Content-Type: {content_type}\n")
        sys.stderr.flush()

    try:
        request_id = (
            request.headers.get("x-request-id", f"req-{id(request)}")
            if "/files/upload" in str(request.url.path)
            else None
        )
        response = await call_next(request)
        if "/files/upload" in str(request.url.path) and request_id:
            logger.info(f"[{request_id}] === MIDDLEWARE: RESPONSE ====")
            logger.info(f"[{request_id}] Status code: {response.status_code}")
            logger.info(f"[{request_id}] Response headers: {dict(response.headers)}")
            if response.status_code == 422:
                logger.error(f"[{request_id}] 422 ERROR in middleware")
                sys.stderr.write(f"[{request_id}] MIDDLEWARE: 422 error detected\n")
                sys.stderr.flush()
        return response
    except RequestValidationError as e:
        if "/files/upload" in str(request.url.path):
            request_id = request.headers.get("x-request-id", f"req-{id(request)}")
            logger.error(f"[{request_id}] === MIDDLEWARE: RequestValidationError ===")
            logger.error(f"[{request_id}] Errors: {e.errors()}", exc_info=True)
            sys.stderr.write(f"[{request_id}] MIDDLEWARE: RequestValidationError\n")
            sys.stderr.write(f"[{request_id}] Errors: {e.errors()}\n")
            sys.stderr.flush()
        raise
    except Exception as e:
        if "/files/upload" in str(request.url.path):
            request_id = request.headers.get("x-request-id", f"req-{id(request)}")
            logger.error(f"[{request_id}] === MIDDLEWARE: Exception ===")
            logger.error(f"[{request_id}] Exception: {str(e)}", exc_info=True)
            sys.stderr.write(f"[{request_id}] MIDDLEWARE: Exception: {str(e)}\n")
            sys.stderr.flush()
        raise

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors (422) with detailed logging"""
    request_id = request.headers.get("x-request-id", f"req-{id(request)}")
    error_details = exc.errors()

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
        if hasattr(request, "_body"):
            body_preview = str(request._body)[:500] if request._body else "None"
            logger.error(f"[{request_id}] Request body (first 500 chars): {body_preview}")
            sys.stderr.write(f"[{request_id}] Request body preview: {body_preview}\n")
            sys.stderr.flush()
    except Exception as e:
        logger.error(f"[{request_id}] Could not read request body: {e}")

    logger.error(f"[{request_id}] === EXCEPTION HANDLER: Returning 422 response ===")
    origin = resolve_error_cors_origin(request.headers.get("origin", "*"))
    return JSONResponse(
        status_code=422,
        content={"detail": error_details},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "*",
        },
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with CORS headers"""
    origin = resolve_error_cors_origin(request.headers.get("origin", "*"))
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "*",
        },
    )

async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with CORS headers"""
    exc_type, exc_value, exc_tb = exc.__class__, exc, exc.__traceback__
    full_traceback = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.error(f"Unhandled exception: {str(exc)}\n{full_traceback}")
    
    # Also print to stderr for immediate visibility
    print(f"ERROR: Unhandled exception: {str(exc)}", file=sys.stderr)
    print(full_traceback, file=sys.stderr)
    
    origin = resolve_error_cors_origin(request.headers.get("origin", "*"))
    
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
            "Access-Control-Allow-Headers": "*",
        },
    )

def register_error_handlers(app: FastAPI):
    """Register middleware and exception handlers on the app."""
    app.middleware("http")(security_middleware)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
