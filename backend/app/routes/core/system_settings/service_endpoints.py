"""Service endpoint registry API."""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query

from backend.app.models.service_endpoint import (
    EndpointAudience,
    ServiceEndpoint,
    ServiceEndpointSnapshot,
    ServiceEndpointUpdate,
    ServiceEndpointURLResponse,
)
from backend.app.services.service_endpoint_registry import service_endpoint_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/service-endpoints", tags=["service-endpoints"])


@router.get("", response_model=ServiceEndpointSnapshot)
@router.get("/", response_model=ServiceEndpointSnapshot)
async def get_service_endpoint_snapshot() -> ServiceEndpointSnapshot:
    """Return the full service endpoint registry snapshot."""
    try:
        return service_endpoint_registry.get_snapshot()
    except Exception as exc:
        logger.error("Failed to get service endpoint snapshot: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get service endpoint snapshot: {exc}",
        )


@router.get("/{service_id}/url", response_model=ServiceEndpointURLResponse)
async def get_service_endpoint_url(
    service_id: str,
    audience: EndpointAudience = Query(..., description="Target endpoint audience"),
) -> ServiceEndpointURLResponse:
    """Resolve one service endpoint URL."""
    endpoint = service_endpoint_registry.get_endpoint(service_id, audience)
    if endpoint is None:
        raise HTTPException(
            status_code=404,
            detail=f"Service endpoint not found: {service_id}/{audience}",
        )
    return ServiceEndpointURLResponse(
        service_id=endpoint.service_id,
        audience=endpoint.audience,
        url=endpoint.url,
        source=endpoint.source,
    )


@router.get("/{service_id}", response_model=List[ServiceEndpoint])
async def list_service_endpoints(service_id: str) -> List[ServiceEndpoint]:
    """Return all endpoints for one service id."""
    endpoints = service_endpoint_registry.list_service_endpoints(service_id)
    if not endpoints:
        raise HTTPException(status_code=404, detail=f"Service endpoint not found: {service_id}")
    return endpoints


@router.put("/{service_id}/{audience}", response_model=ServiceEndpoint)
async def update_service_endpoint_url(
    service_id: str,
    audience: EndpointAudience,
    payload: ServiceEndpointUpdate,
) -> ServiceEndpoint:
    """Persist an endpoint URL override."""
    try:
        return service_endpoint_registry.update_endpoint_url(
            service_id=service_id,
            audience=audience,
            url=payload.url,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to update service endpoint: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update service endpoint: {exc}",
        )
