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
        """Check vector readiness through the shared bounded probe."""
        try:
            from backend.app.services.vector_readiness_probe import (
                get_vector_readiness,
            )

            readiness = get_vector_readiness()
            if not readiness.connected:
                issues.append(
                    HealthIssue(
                        issue_type=(
                            "vector_db_check_failed"
                            if readiness.error
                            else "pgvector_not_installed"
                        ),
                        severity=HealthIssueSeverity.WARNING,
                        message=(
                            "Vector DB connection check failed, semantic search may be unavailable"
                            if readiness.error
                            else "pgvector extension not installed, semantic search unavailable"
                        ),
                        action_url="/settings?tab=database",
                    )
                )
            return readiness.to_dict()
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
