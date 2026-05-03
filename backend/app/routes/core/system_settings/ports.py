"""
Port configuration API.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
import logging

from backend.app.models.port_config import PortConfig, ServiceURLConfig
from backend.app.services.port_config_service import port_config_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ports", tags=["ports"])


@router.get("/", response_model=PortConfig)
async def get_port_config(
    cluster: Optional[str] = Query(None, description="Cluster identifier"),
    environment: Optional[str] = Query(None, description="Environment identifier"),
    site: Optional[str] = Query(None, description="Site identifier")
):
    """
    Get port configuration.

    Args:
        cluster: Optional cluster identifier.
        environment: Optional environment identifier.
        site: Optional site identifier.
    """
    try:
        return port_config_service.get_port_config(
            cluster=cluster,
            environment=environment,
            site=site
        )
    except Exception as e:
        logger.error(f"Failed to get port configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get port configuration: {str(e)}")


@router.put("/", response_model=Dict[str, Any])
async def update_port_config(
    config: PortConfig,
    auto_apply: bool = Query(False, description="Automatically apply changes to docker-compose or Ingress"),
    auto_restart: bool = Query(False, description="Automatically restart services; requires auto_apply=True")
):
    """
    Update port configuration.

    Args:
        config: Port configuration.
        auto_apply: Whether to apply changes to docker-compose or Ingress.
        auto_restart: Whether to restart services; requires auto_apply=True.
    """
    try:
        # Validate port conflicts.
        is_valid, conflicts = port_config_service.validate_port_conflict(config)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Port configuration conflict",
                    "conflicts": conflicts
                }
            )

        # Update configuration.
        success, message = port_config_service.update_port_config(config)
        if not success:
            raise HTTPException(status_code=500, detail=message or "Failed to update port configuration")

        result = {
            "success": True,
            "message": message or "Port configuration updated",
            "config": port_config_service.get_port_config(
                cluster=config.cluster,
                environment=config.environment,
                site=config.site
            ).model_dump()
        }

        # Apply orchestration changes if requested.
        if auto_apply:
            try:
                from backend.app.services.service_orchestration_service import service_orchestration_service
                host_config = port_config_service.get_host_config()
                orchestration_results = service_orchestration_service.apply_port_changes(
                    config,
                    host_config,
                    auto_restart=auto_restart
                )
                result["orchestration"] = orchestration_results
            except Exception as e:
                logger.warning(f"Failed to auto-apply port changes: {e}", exc_info=True)
                result["orchestration"] = {"error": f"Auto-apply failed: {str(e)}"}

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update port configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update port configuration: {str(e)}")


@router.post("/validate", response_model=Dict[str, Any])
async def validate_port_config(config: PortConfig):
    """Validate port configuration and check for conflicts."""
    try:
        is_valid, conflicts = port_config_service.validate_port_conflict(config)
        return {
            "valid": is_valid,
            "conflicts": conflicts
        }
    except Exception as e:
        logger.error(f"Failed to validate port configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to validate port configuration: {str(e)}")


@router.get("/urls", response_model=ServiceURLConfig)
async def get_service_urls(
    cluster: Optional[str] = Query(None, description="Cluster identifier"),
    environment: Optional[str] = Query(None, description="Environment identifier"),
    site: Optional[str] = Query(None, description="Site identifier"),
    protocol: str = Query("http", description="Protocol")
):
    """
    Get service URLs using the hostnames from configuration.

    Args:
        cluster: Optional cluster identifier.
        environment: Optional environment identifier.
        site: Optional site identifier.
        protocol: Protocol. Defaults to http.
    """
    try:
        return port_config_service.get_all_service_urls(
            cluster=cluster,
            environment=environment,
            site=site,
            protocol=protocol
        )
    except Exception as e:
        logger.error(f"Failed to get service URLs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get service URLs: {str(e)}")
