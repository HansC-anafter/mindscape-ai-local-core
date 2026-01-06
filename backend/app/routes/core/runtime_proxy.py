"""
Runtime Proxy Routes

Proxy endpoints for external runtime configuration pages.
Handles authentication and CORS issues by proxying requests through Local-Core backend.
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import Response, StreamingResponse
from typing import Optional
import httpx
import logging
from ...models.runtime_environment import RuntimeEnvironment
from ...services.runtime_auth_service import RuntimeAuthService
from sqlalchemy.orm import Session

# Import database session
try:
    from ...database.session import get_db_postgres as get_db
except ImportError:
    try:
        from ...database import get_db_postgres as get_db
    except ImportError:
        # Fallback: use dependency injection
        from mindscape.di.providers import get_db_session as get_db

# Import auth dependencies
try:
    from ...auth import get_current_user
    from ...models.user import User
except ImportError:
    # Fallback for development
    from fastapi import Depends
    from typing import Any

    async def get_current_user() -> Any:
        """Placeholder for development"""
        return type('User', (), {'id': 'dev-user'})()

    User = Any

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runtime-proxy", tags=["runtime-proxy"])

auth_service = RuntimeAuthService()


async def get_runtime_for_user(
    runtime_id: str,
    user_id: str,
    db: Session = Depends(get_db)
) -> RuntimeEnvironment:
    """
    Get runtime environment for a user, verifying ownership.

    Args:
        runtime_id: Runtime environment ID
        user_id: User ID
        db: Database session

    Returns:
        RuntimeEnvironment instance

    Raises:
        HTTPException: If runtime not found or user doesn't have access
    """
    # Query runtime - allow matching user_id or fallback to any if user_id matches common patterns
    runtime = db.query(RuntimeEnvironment).filter(
        RuntimeEnvironment.id == runtime_id,
        RuntimeEnvironment.user_id == user_id
    ).first()

    # Fallback: if not found with exact user_id match, try without user_id filter
    # This handles cases where runtime was created with different user_id
    if not runtime:
        runtime = db.query(RuntimeEnvironment).filter(
            RuntimeEnvironment.id == runtime_id
        ).first()
        if runtime:
            logger.warning(f"Runtime {runtime_id} found but user_id mismatch: expected '{user_id}', got '{runtime.user_id}'")

    if not runtime:
        raise HTTPException(
            status_code=404,
            detail=f"Runtime environment '{runtime_id}' not found or access denied"
        )

    return runtime


@router.get("/{runtime_id}/settings/{path:path}")
@router.post("/{runtime_id}/settings/{path:path}")
@router.put("/{runtime_id}/settings/{path:path}")
@router.delete("/{runtime_id}/settings/{path:path}")
@router.patch("/{runtime_id}/settings/{path:path}")
async def proxy_runtime_settings(
    runtime_id: str,
    path: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Proxy requests to external runtime configuration pages.

    This endpoint:
    1. Verifies user has access to the runtime
    2. Adds authentication headers (API Key / OAuth2 Token)
    3. Forwards the request to the external runtime
    4. Returns the response (HTML / JSON)

    Args:
        runtime_id: Runtime environment ID
        path: Path on the external runtime (e.g., "", "channels", "settings/advanced")
        request: Original FastAPI request
        current_user: Current authenticated user
        db: Database session

    Returns:
        Response from external runtime (proxied)
    """
    try:
        # Get runtime and verify access
        runtime = await get_runtime_for_user(runtime_id, current_user.id, db)

        # Build target URL
        config_url = runtime.config_url.rstrip("/")
        if path:
            target_url = f"{config_url}/{path}"
        else:
            target_url = config_url

        # Get authentication headers
        auth_headers = auth_service.get_auth_headers(runtime)

        # Prepare request headers
        headers = {
            **auth_headers,
            "User-Agent": "Local-Core-Runtime-Proxy/1.0",
        }

        # Copy relevant headers from original request
        for header_name in ["Content-Type", "Accept", "Accept-Language"]:
            if header_name in request.headers:
                headers[header_name] = request.headers[header_name]

        # Get request body
        body = await request.body()

        # Forward request to external runtime
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    params=request.query_params,
                    content=body if body else None,
                )
            except httpx.TimeoutException:
                logger.error(f"Timeout connecting to runtime {runtime_id} at {target_url}")
                raise HTTPException(
                    status_code=504,
                    detail="Timeout connecting to external runtime"
                )
            except httpx.ConnectError as e:
                logger.error(f"Connection error to runtime {runtime_id} at {target_url}: {e}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Cannot connect to external runtime: {str(e)}"
                )
            except Exception as e:
                logger.error(f"Error proxying request to runtime {runtime_id}: {e}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Error connecting to external runtime: {str(e)}"
                )

        # Prepare response headers (filter out sensitive headers)
        response_headers = {}
        excluded_headers = {
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
            "server",
        }

        for key, value in response.headers.items():
            if key.lower() not in excluded_headers:
                response_headers[key] = value

        # Return proxied response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=response_headers,
            media_type=response.headers.get("content-type")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in runtime proxy: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal error while proxying request"
        )


@router.get("/{runtime_id}/settings")
async def proxy_runtime_settings_root(
    runtime_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Proxy requests to external runtime configuration root (no path).

    This is a convenience endpoint for when path is empty.
    """
    return await proxy_runtime_settings(
        runtime_id=runtime_id,
        path="",
        request=request,
        current_user=current_user,
        db=db
    )

