"""
Vector Database API routes

Handles configuration and testing of vector database connections.

Note: This is a stub implementation. Vector database functionality requires
a vector store adapter to be installed and configured.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from contextlib import contextmanager
from pydantic import BaseModel
import asyncio
import os

from app.database.config import get_vector_postgres_config
from backend.app.database.vector_connection import get_vector_dbapi_connection
from backend.app.services.vector_readiness_probe import (
    get_vector_readiness,
    run_vector_connection_test,
)

router = APIRouter(prefix="/api/v1/vector-db", tags=["Vector Database"])


def get_local_postgres_config() -> Dict[str, Any]:
    """Return local vector database connection parameters."""
    return get_vector_postgres_config()


@contextmanager
def get_connection():
    """Get a psycopg2 connection for vector database operations."""
    conn = get_vector_dbapi_connection()
    try:
        yield conn
    finally:
        conn.close()


def _check_vector_store_adapter() -> bool:
    """Return cached readiness for legacy in-process callers."""
    return get_vector_readiness().connected


class VectorDBConfigRequest(BaseModel):
    """Request model for vector database configuration"""
    mode: str = "local"  # local or custom
    enabled: bool = True
    host: Optional[str] = None
    port: int = 5432
    database: str = "mindscape_vectors"
    schema_name: str = "public"
    username: Optional[str] = None
    password: Optional[str] = None
    ssl_mode: str = "prefer"  # disable, prefer, require
    access_mode: str = "read_write"  # read_write, read_only, disabled
    data_scope: str = "all"  # mindscape_only, with_documents, all


class VectorDBConfigResponse(BaseModel):
    """Response model for vector database configuration"""
    mode: str
    enabled: bool
    host: Optional[str] = None
    port: int = 5432
    database: str = "mindscape_vectors"
    schema_name: str = "public"
    username: Optional[str] = None
    password: Optional[str] = None
    ssl_mode: str = "prefer"
    access_mode: str = "read_write"
    data_scope: str = "all"
    adapter_available: bool = False


@router.get("/config", response_model=VectorDBConfigResponse)
async def get_config():
    """
    Get current vector database configuration

    Returns 501 if no vector store adapter is configured.
    """
    readiness = await asyncio.to_thread(get_vector_readiness)
    if not readiness.connected:
        raise HTTPException(
            status_code=501,
            detail="Vector database adapter not configured. Please install and configure a vector store adapter."
        )

    # TODO: Implement actual config retrieval when adapter is available
    return VectorDBConfigResponse(
        mode="local",
        enabled=True,
        adapter_available=readiness.connected,
    )


@router.put("/config", response_model=VectorDBConfigResponse)
async def update_config(config: VectorDBConfigRequest):
    """
    Update vector database configuration

    Returns 501 if no vector store adapter is configured.
    """
    readiness = await asyncio.to_thread(get_vector_readiness)
    if not readiness.connected:
        raise HTTPException(
            status_code=501,
            detail="Vector database adapter not configured. Please install and configure a vector store adapter."
        )

    # TODO: Implement actual config update when adapter is available
    response = config.model_dump()
    response["password"] = None  # Don't return password
    response["adapter_available"] = True
    return VectorDBConfigResponse(**response)


@router.post("/test", response_model=Dict[str, Any])
async def test_connection(config_request: Optional[VectorDBConfigRequest] = None):
    """
    Test vector database connection

    Tests PostgreSQL connection and checks for pgvector extension.
    """
    custom_config = None
    if config_request and config_request.mode == "custom":
        custom_config = {
            "host": config_request.host or os.getenv("POSTGRES_HOST", "postgres"),
            "port": config_request.port or int(os.getenv("POSTGRES_PORT", "5432")),
            "database": config_request.database
            or os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": config_request.username or os.getenv("POSTGRES_USER", "mindscape"),
            "password": config_request.password
            or os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
            "sslmode": config_request.ssl_mode,
        }

    result = await asyncio.to_thread(run_vector_connection_test, custom_config)
    if custom_config is None:
        database = get_vector_postgres_config().get("database") or "mindscape_vectors"
    else:
        database = custom_config["database"]
    result["database"] = database
    return result
