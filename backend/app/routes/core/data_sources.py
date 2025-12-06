"""
Data Source API Routes
Endpoints for managing data sources

Phase 1: Declarative approach - uses ToolConnection as underlying storage.
Provides DataSource abstraction as a view/service interface.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path as PathParam
from pydantic import BaseModel

from ...models.data_source import (
    DataSource,
    CreateDataSourceRequest,
    UpdateDataSourceRequest
)
from ...services.data_source_service import DataSourceService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/data-sources",
    tags=["data-sources"]
)


# Initialize service
def get_data_source_service() -> DataSourceService:
    """Get DataSourceService instance"""
    return DataSourceService()


@router.post("/", response_model=DataSource, status_code=201)
async def create_data_source(
    request: CreateDataSourceRequest,
    profile_id: str = Query(..., description="Profile ID")
):
    """
    Create a new data source

    Creates a ToolConnection with data_source_type set, then returns as DataSource view.
    """
    try:
        service = get_data_source_service()
        data_source = service.create_data_source(request, profile_id)
        return data_source
    except Exception as e:
        logger.error(f"Failed to create data source: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[DataSource])
async def list_data_sources(
    profile_id: str = Query(..., description="Profile ID"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    type: Optional[str] = Query(None, description="Filter by data source type"),
    active_only: bool = Query(True, description="Return only active data sources"),
    workspace_id: Optional[str] = Query(None, description="Workspace ID (for applying overlay)")
):
    """
    List all data sources for a profile

    Optionally filter by tenant_id and data source type.
    Applies workspace overlay if workspace_id is provided.
    """
    try:
        service = get_data_source_service()
        data_sources = service.list_data_sources(
            profile_id=profile_id,
            tenant_id=tenant_id,
            data_source_type=type,
            active_only=active_only,
            workspace_id=workspace_id
        )
        return data_sources
    except Exception as e:
        logger.error(f"Failed to list data sources: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{data_source_id}", response_model=DataSource)
async def get_data_source(
    data_source_id: str = PathParam(..., description="Data source ID"),
    profile_id: str = Query(..., description="Profile ID"),
    workspace_id: Optional[str] = Query(None, description="Workspace ID (for applying overlay)")
):
    """
    Get a specific data source by ID

    Applies workspace overlay if workspace_id is provided.
    """
    try:
        service = get_data_source_service()
        data_source = service.get_data_source(data_source_id, profile_id, workspace_id=workspace_id)

        if not data_source:
            raise HTTPException(
                status_code=404,
                detail=f"Data source {data_source_id} not found"
            )

        return data_source
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get data source: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{data_source_id}", response_model=DataSource)
async def update_data_source(
    data_source_id: str = PathParam(..., description="Data source ID"),
    request: UpdateDataSourceRequest = ...,
    profile_id: str = Query(..., description="Profile ID")
):
    """
    Update a data source

    Updates underlying ToolConnection and returns as DataSource view.
    """
    try:
        service = get_data_source_service()
        data_source = service.update_data_source(
            data_source_id,
            profile_id,
            request
        )

        if not data_source:
            raise HTTPException(
                status_code=404,
                detail=f"Data source {data_source_id} not found"
            )

        return data_source
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update data source: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{data_source_id}", status_code=204)
async def delete_data_source(
    data_source_id: str = PathParam(..., description="Data source ID"),
    profile_id: str = Query(..., description="Profile ID")
):
    """
    Delete a data source

    Deletes underlying ToolConnection.
    """
    try:
        service = get_data_source_service()
        deleted = service.delete_data_source(data_source_id, profile_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Data source {data_source_id} not found"
            )

        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete data source: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-type/{data_source_type}", response_model=List[DataSource])
async def get_data_sources_by_type(
    data_source_type: str = PathParam(..., description="Data source type"),
    profile_id: str = Query(..., description="Profile ID"),
    active_only: bool = Query(True, description="Return only active data sources")
):
    """
    Get all data sources of a specific type

    Convenience endpoint for filtering by type.
    """
    try:
        service = get_data_source_service()
        data_sources = service.get_data_source_by_type(
            profile_id=profile_id,
            data_source_type=data_source_type,
            active_only=active_only
        )
        return data_sources
    except Exception as e:
        logger.error(f"Failed to get data sources by type: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

