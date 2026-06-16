from __future__ import annotations

from typing import List, Optional

from .models import AgentClient


class ConnectionLookupMixin:
    def has_connections(
        self,
        workspace_id: Optional[str] = None,
        surface_type: Optional[str] = None,
    ) -> bool:
        """Check if there are any authenticated connections (cross-worker).

        Queries the PostgreSQL ws_connections table so that ALL uvicorn
        workers return a consistent answer. Falls back to in-memory
        check if the DB query fails.
        """
        try:
            return self._db_has_connections(
                workspace_id=workspace_id,
                surface_type=surface_type,
            )
        except Exception:
            # Fallback to local in-memory check on DB failure
            if workspace_id:
                clients = self._clients.get(workspace_id, {})
                return any(
                    c.authenticated
                    and (not surface_type or c.surface_type == surface_type)
                    for c in clients.values()
                )
            return any(
                c.authenticated
                and (not surface_type or c.surface_type == surface_type)
                for ws_clients in self._clients.values()
                for c in ws_clients.values()
            )

    def has_local_connections(
        self,
        workspace_id: Optional[str] = None,
        surface_type: Optional[str] = None,
    ) -> bool:
        """Check in-memory only (current worker). Used for local dispatch."""
        if workspace_id:
            clients = self._clients.get(workspace_id, {})
            return any(
                c.authenticated
                and (not surface_type or c.surface_type == surface_type)
                for c in clients.values()
            )
        return any(
            c.authenticated
            and (not surface_type or c.surface_type == surface_type)
            for ws_clients in self._clients.values()
            for c in ws_clients.values()
        )

    def get_connected_workspaces(self) -> List[str]:
        """Return list of workspace IDs that have authenticated clients."""
        return [
            ws_id
            for ws_id, clients in self._clients.items()
            if any(c.authenticated for c in clients.values())
        ]

    def get_client(
        self,
        workspace_id: str,
        client_id: Optional[str] = None,
        surface_type: Optional[str] = None,
    ) -> Optional[AgentClient]:
        """
        Get a specific client, or the best available client for a workspace.

        Only returns clients from this worker's in-memory store.
        If client_id is specified, returns that exact client.
        Otherwise, returns the most recently active authenticated client.
        """
        ws_clients = self._clients.get(workspace_id, {})

        if client_id:
            client = ws_clients.get(client_id)
            if (
                client
                and client.authenticated
                and (not surface_type or client.surface_type == surface_type)
            ):
                return client
            return None

        # Find best available: most recent heartbeat
        authenticated = [
            c
            for c in ws_clients.values()
            if c.authenticated and (not surface_type or c.surface_type == surface_type)
        ]
        if not authenticated:
            return None

        return max(authenticated, key=lambda c: c.last_heartbeat)

    # ============================================================
    #  PostgreSQL cross-worker helpers
    # ============================================================
