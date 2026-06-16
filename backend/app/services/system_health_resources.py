from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from backend.app.services.system_health_models import HealthIssue, HealthIssueSeverity

logger = logging.getLogger("backend.app.services.system_health_checker")


class SystemHealthResourceMixin:
    @staticmethod
    def _ocr_service_required() -> bool:
        raw = os.getenv("OCR_SERVICE_REQUIRED", "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _ocr_service_is_default_optional(ocr_client: Any) -> bool:
        if os.getenv("OCR_SERVICE_URL"):
            return False
        service_url = str(getattr(ocr_client, "service_url", "") or "").rstrip("/")
        return service_url == "http://ocr-service:8001"

    def _optional_ocr_disabled_response(self, ocr_client: Any) -> Optional[Dict[str, Any]]:
        if self._ocr_service_required():
            return None
        if not self._ocr_service_is_default_optional(ocr_client):
            return None
        return {
            "status": "disabled",
            "available": False,
            "required": False,
            "service": "ocr-service",
            "reason": "OCR service is optional and no OCR_SERVICE_URL is configured.",
        }

    async def _check_vector_db(self, issues: List[HealthIssue]) -> Dict[str, Any]:
        """Check Vector DB connection using actual connection test"""
        try:
            # Use comprehensive connection test including pgvector extension check
            try:
                from backend.app.routes.vector_db import get_config, get_local_postgres_config
                import psycopg2
                from psycopg2.extras import RealDictCursor

                # Get current config
                config = await get_config()

                # Determine connection parameters
                if config.mode == "local":
                    local_config = get_local_postgres_config()
                    conn_params = {
                        "host": local_config["host"],
                        "port": local_config["port"],
                        "database": local_config["database"],
                        "user": local_config["user"],
                        "password": local_config["password"],
                    }
                else:
                    password = config.password
                    if not password:
                        from backend.app.routes.vector_db import get_connection
                        with get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute('SELECT password FROM vector_db_config ORDER BY id DESC LIMIT 1')
                            row = cursor.fetchone()
                            password = row["password"] if row else None

                    if not config.host or not config.username or not password:
                        return {"connected": False}

                    conn_params = {
                        "host": config.host,
                        "port": config.port,
                        "database": config.database,
                        "user": config.username,
                        "password": password,
                    }

                    if config.ssl_mode == "require":
                        conn_params["sslmode"] = "require"
                    elif config.ssl_mode == "prefer":
                        conn_params["sslmode"] = "prefer"

                # Test connection and check pgvector
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

                cursor.close()
                pg_conn.close()

                connected = pgvector_installed

                if not connected:
                    if not pgvector_installed:
                        issues.append(HealthIssue(
                            issue_type="pgvector_not_installed",
                            severity=HealthIssueSeverity.WARNING,
                            message="pgvector extension not installed, semantic search unavailable",
                            action_url="/settings?tab=database"
                        ))

                return {
                    "connected": connected,
                    "pgvector_installed": pgvector_installed,
                    "pgvector_version": pgvector_version
                }
            except ImportError:
                # Fallback to old method if test function not available
                logger.warning("Vector DB comprehensive test not available, using fallback check")
                from backend.app.services.vector_search import VectorSearchService
                vector_service = VectorSearchService()
                connected = await vector_service.check_connection()

                if not connected:
                    issues.append(HealthIssue(
                        issue_type="vector_db_not_connected",
                        severity=HealthIssueSeverity.WARNING,
                        message="Vector DB not connected, semantic search may be unavailable",
                        action_url="/settings?tab=database"
                    ))

                return {
                    "connected": connected
                }
            except Exception as conn_error:
                logger.warning(f"Vector DB comprehensive test failed: {conn_error}")
                # Fallback to simple check
                from backend.app.services.vector_search import VectorSearchService
                vector_service = VectorSearchService()
                connected = await vector_service.check_connection()

                if not connected:
                    issues.append(HealthIssue(
                        issue_type="vector_db_not_connected",
                        severity=HealthIssueSeverity.WARNING,
                        message="Vector DB connection check failed, semantic search may be unavailable",
                        action_url="/settings?tab=database"
                    ))

                return {
                    "connected": connected
                }
        except ImportError:
            logger.warning("Vector DB check not available")
            return {"connected": False}
        except Exception as e:
            logger.error(f"Failed to check Vector DB: {e}", exc_info=True)
            issues.append(HealthIssue(
                issue_type="vector_db_check_failed",
                severity=HealthIssueSeverity.WARNING,
                message=f"Error checking Vector DB connection: {str(e)}",
                action_url="/settings?tab=database"
            ))
            return {"connected": False}

    async def _check_backend_service(self, issues: List[HealthIssue]) -> Dict[str, Any]:
        """Check backend API service health"""
        # If we're already in the backend service checking itself, just return healthy
        # to avoid infinite loop or unnecessary HTTP calls
        # Resolve the backend URL from port configuration.
        try:
            from .port_config_service import port_config_service
            import os
            current_cluster = os.getenv('CLUSTER_NAME')
            current_env = os.getenv('ENVIRONMENT')
            current_site = os.getenv('SITE_NAME')
            url = port_config_service.get_service_url(
                'backend_api',
                cluster=current_cluster,
                environment=current_env,
                site=current_site
            )
        except Exception:
            try:
                from .service_endpoint_registry import service_endpoint_registry

                url = (
                    service_endpoint_registry.get_endpoint_url(
                        "local_core.execution_api", "host_public"
                    )
                    or ""
                )
            except Exception:
                url = ""

        return {
            "status": "healthy",
            "available": True,
            "url": url
        }

    async def _check_ocr_service(self, issues: List[HealthIssue]) -> Dict[str, Any]:
        """Check OCR service health"""
        try:
            from backend.app.capabilities.core_files.services.ocr_client import get_ocr_client

            ocr_client = get_ocr_client()
            optional_disabled = self._optional_ocr_disabled_response(ocr_client)
            if optional_disabled:
                return optional_disabled

            health_data = await ocr_client.check_health()

            if health_data.get("status") == "ok":
                return {
                    "status": "healthy",
                    "available": True,
                    "gpu_available": health_data.get("gpu_available", False),
                    "gpu_enabled": health_data.get("gpu_enabled", False),
                    "service": health_data.get("service", "ocr-service")
                }
            else:
                issues.append(HealthIssue(
                    issue_type="ocr_service_unhealthy",
                    severity=HealthIssueSeverity.WARNING,
                    message=f"OCR service unhealthy: {health_data.get('error', 'unknown')}",
                    action_url="/settings?tab=service_status"
                ))
                return {
                    "status": "unhealthy",
                    "available": False,
                    "error": health_data.get("error", "unknown")
                }
        except Exception as e:
            logger.warning(f"OCR service health check failed: {e}")
            optional_disabled = self._optional_ocr_disabled_response(
                locals().get("ocr_client")
            )
            if optional_disabled:
                return optional_disabled
            issues.append(HealthIssue(
                issue_type="ocr_service_unavailable",
                severity=HealthIssueSeverity.WARNING,
                message=f"OCR service unavailable: {str(e)}. Local OCR features may not work.",
                action_url="/settings?tab=service_status"
            ))
            return {
                "status": "unavailable",
                "available": False,
                "error": str(e)
            }
