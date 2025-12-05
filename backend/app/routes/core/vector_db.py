"""
Vector Database API routes

Handles configuration and testing of vector database connections.

Note: This is a stub implementation. Vector database functionality requires
a vector store adapter to be installed and configured.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os

router = APIRouter(prefix="/api/v1/vector-db", tags=["Vector Database"])


def _check_vector_store_adapter() -> bool:
    """
    Check if vector store adapter is available

    For now, check if PostgreSQL with pgvector is available and configured.
    In the future, this will check for registered vector store adapters.

    Returns:
        True if adapter is available, False otherwise
    """
    try:
        # Try to connect to PostgreSQL to check if vector store is available
        import psycopg2
        import os

        # Get connection parameters from environment
        host = os.getenv("POSTGRES_HOST", "postgres")
        port = int(os.getenv("POSTGRES_PORT", "5432"))
        database = os.getenv("POSTGRES_DB", "mindscape_vectors")
        user = os.getenv("POSTGRES_USER", "mindscape")
        password = os.getenv("POSTGRES_PASSWORD", "mindscape_password")

        # Try to connect and check if pgvector extension is available
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            connect_timeout=5
        )

        with conn.cursor() as cursor:
            # Check if pgvector extension is installed
            cursor.execute("SELECT * FROM pg_extension WHERE extname = 'vector';")
            result = cursor.fetchone()
            if result:
                return True

        conn.close()
        return False

    except Exception as e:
        # If connection fails, vector store is not available
        return False


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
    if not _check_vector_store_adapter():
        raise HTTPException(
            status_code=501,
            detail="Vector database adapter not configured. Please install and configure a vector store adapter."
        )

    # TODO: Implement actual config retrieval when adapter is available
    return VectorDBConfigResponse(
        mode="local",
        enabled=True,
        adapter_available=_check_vector_store_adapter()
    )


@router.put("/config", response_model=VectorDBConfigResponse)
async def update_config(config: VectorDBConfigRequest):
    """
    Update vector database configuration

    Returns 501 if no vector store adapter is configured.
    """
    if not _check_vector_store_adapter():
        raise HTTPException(
            status_code=501,
            detail="Vector database adapter not configured. Please install and configure a vector store adapter."
        )

    # TODO: Implement actual config update when adapter is available
    response = config.dict()
    response["password"] = None  # Don't return password
    response["adapter_available"] = True
    return VectorDBConfigResponse(**response)


@router.post("/test", response_model=Dict[str, Any])
async def test_connection(config_request: Optional[VectorDBConfigRequest] = None):
    """
    Test vector database connection

    Tests PostgreSQL connection and checks for pgvector extension.
    """
    try:
        # Use config from request or environment variables
        if config_request and config_request.mode == "custom":
            host = config_request.host or os.getenv("POSTGRES_HOST", "postgres")
            port = config_request.port or int(os.getenv("POSTGRES_PORT", "5432"))
            database = config_request.database or os.getenv("POSTGRES_DB", "mindscape_vectors")
            user = config_request.username or os.getenv("POSTGRES_USER", "mindscape")
            password = config_request.password or os.getenv("POSTGRES_PASSWORD", "mindscape_password")
        else:
            # Local mode - use environment variables
            host = os.getenv("POSTGRES_HOST", "postgres")
            port = int(os.getenv("POSTGRES_PORT", "5432"))
            database = os.getenv("POSTGRES_DB", "mindscape_vectors")
            user = os.getenv("POSTGRES_USER", "mindscape")
            password = os.getenv("POSTGRES_PASSWORD", "mindscape_password")

        # Connect to PostgreSQL
        conn_params = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
            "connect_timeout": 5
        }

        if config_request and config_request.ssl_mode == "require":
            conn_params["sslmode"] = "require"
        elif config_request and config_request.ssl_mode == "prefer":
            conn_params["sslmode"] = "prefer"

        pg_conn = psycopg2.connect(**conn_params)
        cursor = pg_conn.cursor(cursor_factory=RealDictCursor)

        # Check pgvector extension
        cursor.execute("""
            SELECT EXISTS(
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            ) as installed
        """)
        pgvector_check = cursor.fetchone()
        pgvector_installed = pgvector_check and pgvector_check["installed"]

        # Get pgvector version if installed
        pgvector_version = None
        if pgvector_installed:
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            version_row = cursor.fetchone()
            pgvector_version = version_row["extversion"] if version_row else None

        # Check dimension compatibility (check if main tables have vector columns)
        dimension_check = False
        dimension = None
        dimension_error = None
        try:
            # Check mindscape_personal table for vector dimension
            cursor.execute("""
                SELECT atttypmod - 4 as dimension
                FROM pg_attribute
                WHERE attrelid = 'mindscape_personal'::regclass
                AND attname = 'embedding'
                AND atttypmod > 0
            """)
            dim_row = cursor.fetchone()
            if dim_row and dim_row["dimension"]:
                dimension = dim_row["dimension"]
                dimension_check = True
        except Exception as e:
            dimension_error = f"Could not check dimension: {str(e)}"

        cursor.close()
        pg_conn.close()

        return {
            "success": True,
            "connected": True,
            "database": database,
            "pgvector_installed": pgvector_installed,
            "pgvector_version": pgvector_version,
            "dimension_check": dimension_check,
            "dimension": dimension,
            "dimension_error": dimension_error
        }

    except psycopg2.OperationalError as e:
        return {
            "success": False,
            "connected": False,
            "error": f"Connection failed: {str(e)}",
            "pgvector_installed": False
        }
    except Exception as e:
        return {
            "success": False,
            "connected": False,
            "error": f"Test failed: {str(e)}",
            "pgvector_installed": False
        }

