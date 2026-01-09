"""
Mindscape Dependency Injection Layer

Provides environment-adaptive dependency injection mechanism, automatically
provides correct dependency implementations based on environment (Cloud/Local-Core).

Usage:
    from fastapi import APIRouter, Depends
    from mindscape.di import get_tenant_uuid, get_db_session

    router = APIRouter()

    @router.get("/items")
    async def list_items(
        tenant_uuid: str = Depends(get_tenant_uuid),
        db = Depends(get_db_session)
    ):
        # Works correctly in both Cloud and Local-Core environments
        pass
"""

from .providers import (
    get_tenant_uuid,
    get_db_session,
    get_execution_context,
    is_cloud_environment,
    is_local_core_environment,
    TenantUUIDProvider,
    DBSessionProvider,
    ExecutionContextProvider,
)

__all__ = [
    "get_tenant_uuid",
    "get_db_session",
    "get_execution_context",
    "is_cloud_environment",
    "is_local_core_environment",
    "TenantUUIDProvider",
    "DBSessionProvider",
    "ExecutionContextProvider",
]



