"""
Data Source Service
Service layer for data source management

Phase 1: Declarative approach - uses ToolConnection as underlying storage.
Provides DataSource abstraction as a view/service interface.
"""

import logging
from typing import List, Optional
from datetime import datetime

from ..models.data_source import DataSource, CreateDataSourceRequest, UpdateDataSourceRequest
from ..models.tool_connection import ToolConnection
from .tool_connection_store import ToolConnectionStore

logger = logging.getLogger(__name__)


class DataSourceService:
    """
    Data Source Service - view layer over ToolConnection

    Provides data source abstraction while using ToolConnection as underlying storage.
    This allows gradual migration without breaking existing functionality.
    """

    def __init__(self, db_path: str = "data/my_agent_console.db"):
        """Initialize DataSourceService with database path"""
        self.store = ToolConnectionStore(db_path=db_path)

    def create_data_source(
        self,
        request: CreateDataSourceRequest,
        profile_id: str
    ) -> DataSource:
        """
        Create a new data source

        Creates a ToolConnection with data_source_type set, then returns as DataSource view.
        """
        # Create ToolConnection with data_source_type
        connection = ToolConnection(
            id=f"{request.type}:{request.name.lower().replace(' ', '-')}",
            profile_id=profile_id,
            tool_type=request.type,
            connection_type=request.connection_type,
            name=request.name,
            description=request.description,
            icon=request.icon,
            config=request.config,
            data_source_type=request.type,
            tenant_id=request.tenant_id,
            owner_profile_id=request.owner_profile_id or profile_id,
            is_active=True,
            is_validated=False,
        )

        # Save to store
        saved_connection = self.store.save_connection(connection)

        # Return as DataSource view
        return DataSource.from_tool_connection(saved_connection)

    def get_data_source(
        self,
        data_source_id: str,
        profile_id: str,
        workspace_id: Optional[str] = None
    ) -> Optional[DataSource]:
        """
        Get a data source by ID

        Reads from ToolConnection and returns as DataSource view.
        Applies workspace overlay if workspace_id is provided.
        """
        connection = self.store.get_connection(data_source_id, profile_id)
        if not connection:
            return None

        # Check if it's actually a data source
        if not connection.data_source_type:
            return None

        data_source = DataSource.from_tool_connection(connection)

        # Apply workspace overlay if workspace_id is provided
        if workspace_id:
            from backend.app.services.data_source_overlay_service import DataSourceOverlayService
            overlay_service = DataSourceOverlayService()
            data_source = overlay_service.apply_data_source_overlay(data_source, workspace_id)

        return data_source

    def list_data_sources(
        self,
        profile_id: str,
        tenant_id: Optional[str] = None,
        data_source_type: Optional[str] = None,
        active_only: bool = True,
        workspace_id: Optional[str] = None
    ) -> List[DataSource]:
        """
        List all data sources for a profile

        Filters by tenant_id and data_source_type if provided.
        Applies workspace overlay if workspace_id is provided.
        """
        # Get all connections for profile
        connections = self.store.get_connections_by_profile(profile_id, active_only=active_only)

        # Filter to data sources only
        data_sources = []
        for conn in connections:
            if not conn.data_source_type:
                continue

            # Apply filters
            if tenant_id and conn.tenant_id != tenant_id:
                continue
            if data_source_type and conn.data_source_type != data_source_type:
                continue

            try:
                data_source = DataSource.from_tool_connection(conn)
                data_sources.append(data_source)
            except Exception as e:
                logger.warning(f"Failed to convert connection {conn.id} to DataSource: {e}")
                continue

        # Apply workspace overlay if workspace_id is provided
        if workspace_id:
            from backend.app.services.data_source_overlay_service import DataSourceOverlayService
            overlay_service = DataSourceOverlayService()
            data_sources = overlay_service.apply_data_sources_overlay(data_sources, workspace_id)

        return data_sources

    def update_data_source(
        self,
        data_source_id: str,
        profile_id: str,
        request: UpdateDataSourceRequest
    ) -> Optional[DataSource]:
        """
        Update a data source

        Updates underlying ToolConnection and returns as DataSource view.
        """
        connection = self.store.get_connection(data_source_id, profile_id)
        if not connection:
            return None

        # Check if it's actually a data source
        if not connection.data_source_type:
            return None

        # Update fields
        if request.name is not None:
            connection.name = request.name
        if request.description is not None:
            connection.description = request.description
        if request.icon is not None:
            connection.icon = request.icon
        if request.config is not None:
            connection.config = request.config
        if request.is_active is not None:
            connection.is_active = request.is_active
        if request.tenant_id is not None:
            connection.tenant_id = request.tenant_id
        if request.owner_profile_id is not None:
            connection.owner_profile_id = request.owner_profile_id

        connection.updated_at = datetime.utcnow()

        # Save updated connection
        saved_connection = self.store.save_connection(connection)

        # Return as DataSource view
        return DataSource.from_tool_connection(saved_connection)

    def delete_data_source(self, data_source_id: str, profile_id: str) -> bool:
        """
        Delete a data source

        Deletes underlying ToolConnection.
        """
        return self.store.delete_connection(data_source_id, profile_id)

    def get_data_source_by_type(
        self,
        profile_id: str,
        data_source_type: str,
        active_only: bool = True
    ) -> List[DataSource]:
        """
        Get all data sources of a specific type

        Convenience method for filtering by type.
        """
        return self.list_data_sources(
            profile_id=profile_id,
            data_source_type=data_source_type,
            active_only=active_only
        )

