"""
Environment-Adaptive Dependency Injection Providers

Automatically provides correct dependency implementations based on environment.

Cloud environment:
- Extract tenant UUID from HTTP Header
- Connect to tenant-specific database
- Use full ExecutionContext

Local-Core environment:
- Use default single-tenant UUID
- Connect to local SQLite database
- Use Shim ExecutionContext
"""

from typing import Optional, Callable, Any, Generator, AsyncGenerator
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
import os
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Environment Detection (using mindscape abstraction layer)
# ============================================================================

def _get_environment() -> str:
    """
    Get current environment (re-detects on each call).

    Uses mindscape.get_environment(force_reload=True) to ensure environment
    is re-detected on each request, supporting runtime environment changes
    (e.g., tests, container restarts).
    """
    from mindscape import get_environment
    return get_environment(force_reload=True)


def is_cloud_environment() -> bool:
    """Check if running in Cloud environment (re-detects on each call)."""
    return _get_environment() == "cloud"


def is_local_core_environment() -> bool:
    """Check if running in Local-Core environment (re-detects on each call)."""
    return _get_environment() == "local-core"


# ============================================================================
# Tenant UUID Provider
# ============================================================================

class TenantUUIDProvider:
    """
    Multi-environment Tenant UUID provider.

    - Cloud: Extract from HTTP Header
    - Local-Core: Use default single-tenant UUID
    """

    DEFAULT_LOCAL_TENANT = "local-default-tenant"
    HEADER_NAME = "X-Tenant-UUID"

    @classmethod
    def get_provider(cls) -> Callable:
        """Return provider function suitable for current environment."""
        if is_cloud_environment():
            return cls._cloud_provider
        else:
            return cls._local_core_provider

    @staticmethod
    async def _cloud_provider(
        x_tenant_uuid: Optional[str] = Header(None, alias="X-Tenant-UUID")
    ) -> str:
        """Cloud environment: extract tenant UUID from header."""
        if not x_tenant_uuid:
            raise HTTPException(
                status_code=400,
                detail="X-Tenant-UUID header is required"
            )
        return x_tenant_uuid

    @staticmethod
    async def _local_core_provider() -> str:
        """Local-Core environment: return default tenant UUID."""
        return TenantUUIDProvider.DEFAULT_LOCAL_TENANT


async def get_tenant_uuid(
    x_tenant_uuid: Optional[str] = Header(None, alias="X-Tenant-UUID")
) -> str:
    """
    Get Tenant UUID (auto-adapts to environment).

    This function re-detects environment on each request:
    - Cloud: Extract from HTTP Header, raise error if missing
    - Local-Core: Use default single-tenant UUID

    Usage:
        @router.get("/sessions")
        async def list_sessions(tenant_uuid: str = Depends(get_tenant_uuid)):
            ...
    """
    from mindscape import get_environment

    # Re-detect environment on each request (supports runtime environment changes)
    env = get_environment(force_reload=True)

    if env == "cloud":
        if not x_tenant_uuid:
            raise HTTPException(
                status_code=400,
                detail="X-Tenant-UUID header required in cloud environment"
            )
        return x_tenant_uuid
    else:
        # Local-Core environment: ignore header, use default value
        return TenantUUIDProvider.DEFAULT_LOCAL_TENANT


# ============================================================================
# Database Session Provider
# ============================================================================

class DBSessionProvider:
    """
    Multi-environment database session provider.

    - Cloud: Tenant-routed PostgreSQL
    - Local-Core: Local SQLite
    """

    @classmethod
    def get_provider(cls) -> Callable:
        """Return provider function suitable for current environment."""
        if is_cloud_environment():
            return cls._cloud_provider
        else:
            return cls._local_core_provider

    @staticmethod
    async def _cloud_provider(
        tenant_uuid: str = Depends(get_tenant_uuid)
    ) -> Generator:
        """Cloud environment: get tenant-specific database session."""
        try:
            from database.tenant_db_router import get_tenant_session
            session = get_tenant_session(tenant_uuid)
            try:
                yield session
            finally:
                session.close()
        except ImportError:
            logger.error("Failed to import tenant database router")
            raise HTTPException(
                status_code=500,
                detail="Database configuration error"
            )

    @staticmethod
    async def _local_core_provider() -> Generator:
        """Local-Core environment: get local database session."""
        try:
            from backend.app.database import get_session
            session = get_session()
            try:
                yield session
            finally:
                session.close()
        except ImportError:
            try:
                from app.database import get_session
                session = get_session()
                try:
                    yield session
                finally:
                    session.close()
            except ImportError:
                logger.error("Failed to import local database session")
                raise HTTPException(
                    status_code=500,
                    detail="Database configuration error"
                )


async def get_db_session(
    tenant_uuid: str = Depends(get_tenant_uuid)
) -> AsyncGenerator[Session, None]:
    """
    Get database session (auto-adapts to environment).

    This function re-detects environment on each request:
    - Cloud: Use tenant-routed PostgreSQL session (via cloud capability's database_dependency)
    - Local-Core: Use local PostgreSQL session

    Architecture Note:
    - Local-Core should NOT import cloud modules directly
    - Cloud capabilities should provide their own database_dependency.py that handles cloud-specific logic
    - This function only handles local-core database sessions

    Usage:
        @router.get("/sessions")
        async def list_sessions(db = Depends(get_db_session)):
            ...
    """
    # Local-Core: Always use local database session
    # Cloud capabilities should use their own database_dependency.py (not this function)
    from backend.app.database import get_db_postgres
    # get_db_postgres() is a synchronous generator function
    # We need to wrap it for async context
    session_gen = get_db_postgres()
    session = next(session_gen)
    try:
        yield session
    finally:
        try:
            next(session_gen, None)  # Complete the generator cleanup
        except StopIteration:
            pass


# ============================================================================
# Execution Context Provider
# ============================================================================

class ExecutionContextProvider:
    """
    Multi-environment ExecutionContext provider.

    - Cloud: Use full contracts.execution_context
    - Local-Core: Use shim ExecutionContext
    """

    @classmethod
    def get_provider(cls) -> Callable:
        """Return provider function suitable for current environment (re-detects on each call)."""
        from mindscape import get_environment
        # Re-detect environment on each call (supports runtime environment changes)
        env = get_environment(force_reload=True)
        if env == "cloud":
            return cls._cloud_provider
        else:
            return cls._local_core_provider

    @staticmethod
    async def _cloud_provider(
        request: Request,
        tenant_uuid: str = Depends(get_tenant_uuid)
    ):
        """Cloud environment: create full ExecutionContext."""
        try:
            from contracts.execution_context import ExecutionContext
            return ExecutionContext(
                tenant_id=tenant_uuid,
                actor_id=request.headers.get("X-Actor-ID"),
                trace_id=request.headers.get("X-Trace-ID"),
            )
        except ImportError:
            # Fallback to shim
            from mindscape.shims.execution_context import get_execution_context
            return get_execution_context(
                tenant_id=tenant_uuid,
                actor_id=request.headers.get("X-Actor-ID"),
                trace_id=request.headers.get("X-Trace-ID"),
            )

    @staticmethod
    async def _local_core_provider(
        request: Request = None
    ):
        """Local-Core environment: create Shim ExecutionContext."""
        from mindscape.shims.execution_context import get_execution_context

        actor_id = None
        trace_id = None
        if request:
            actor_id = request.headers.get("X-Actor-ID")
            trace_id = request.headers.get("X-Trace-ID")

        return get_execution_context(
            actor_id=actor_id,
            trace_id=trace_id,
        )


async def get_execution_context(
    request: Request,
    tenant_uuid: str = Depends(get_tenant_uuid)
):
    """
    Get ExecutionContext (auto-adapts to environment).

    This function re-detects environment on each request:
    - Cloud: Use full contracts.execution_context
    - Local-Core: Use shim ExecutionContext

    Usage:
        @router.post("/process")
        async def process(ctx = Depends(get_execution_context)):
            ctx.log_event("process_started")
            ...
    """
    from mindscape import get_environment

    # Re-detect environment on each request (supports runtime environment changes)
    env = get_environment(force_reload=True)

    if env == "cloud":
        try:
            from contracts.execution_context import ExecutionContext
            return ExecutionContext(
                tenant_id=tenant_uuid,
                actor_id=request.headers.get("X-Actor-ID"),
                trace_id=request.headers.get("X-Trace-ID"),
            )
        except ImportError:
            # Fallback to shim if contracts not available
            pass

    # Local-Core or fallback: use shim
    from mindscape.shims.execution_context import get_execution_context as get_ctx
    return get_ctx(
        tenant_id=tenant_uuid if env == "cloud" else "local-default-tenant",
        actor_id=request.headers.get("X-Actor-ID"),
        trace_id=request.headers.get("X-Trace-ID"),
    )


# ============================================================================
# Decorator: requires_tenant
# ============================================================================

def requires_tenant(func: Callable) -> Callable:
    """
    Decorator to mark route as requiring tenant context.

    Automatically injects tenant_uuid parameter.

    Usage:
        @router.get("/items")
        @requires_tenant
        async def list_items(tenant_uuid: str, ...):
            pass
    """
    from functools import wraps
    import inspect

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # If tenant_uuid already exists, don't override
        if 'tenant_uuid' not in kwargs:
            from mindscape import get_environment
            # Re-detect environment on each request (supports runtime environment changes)
            env = get_environment(force_reload=True)

            if env == "cloud":
                # Try to get from request
                for arg in args:
                    if hasattr(arg, 'headers'):
                        tenant_uuid = arg.headers.get('X-Tenant-UUID')
                        if tenant_uuid:
                            kwargs['tenant_uuid'] = tenant_uuid
                            break
                if 'tenant_uuid' not in kwargs:
                    raise HTTPException(
                        status_code=400,
                        detail="X-Tenant-UUID header is required"
                    )
            else:
                kwargs['tenant_uuid'] = TenantUUIDProvider.DEFAULT_LOCAL_TENANT

        return await func(*args, **kwargs)

    return wrapper


