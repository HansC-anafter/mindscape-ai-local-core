"""
Ephemeral Workspace Manager — lifecycle management for temporary workspaces.

Handles workspace TTL, auto-teardown, and asset transfer back to parent.
Part of Phase 4 of the asset-boundary-oriented workspace dispatch strategy.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AssetTransferResult:
    """Result of transferring assets from ephemeral to parent workspace."""

    source_workspace_id: str
    target_workspace_id: str
    transferred: List[str] = field(default_factory=list)
    failed: List[Dict[str, str]] = field(default_factory=list)
    status: str = "pending"


class EphemeralWorkspaceManager:
    """Manages lifecycle of ephemeral workspaces created by dispatch.

    Responsibilities:
    - Create ephemeral workspaces with TTL
    - Collect expired workspaces for teardown
    - Transfer asset bindings back to parent workspace
    - Mark workspaces for deletion after transfer
    """

    def __init__(self, workspace_store=None, binding_store=None):
        """Initialize with stores (lazy-loaded if None)."""
        self._workspace_store = workspace_store
        self._binding_store = binding_store

    @property
    def workspace_store(self):
        if self._workspace_store is None:
            from backend.app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            self._workspace_store = PostgresWorkspacesStore()
        return self._workspace_store

    @property
    def binding_store(self):
        if self._binding_store is None:
            from backend.app.services.stores.workspace_resource_binding_store import (
                WorkspaceResourceBindingStore,
            )

            self._binding_store = WorkspaceResourceBindingStore()
        return self._binding_store

    def mark_ephemeral(
        self,
        workspace_id: str,
        ttl_hours: int = 24,
        parent_workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mark an existing workspace as ephemeral with TTL.

        Args:
            workspace_id: Workspace to mark.
            ttl_hours: Hours until auto-teardown.
            parent_workspace_id: Origin workspace for asset transfer.

        Returns:
            Updated workspace metadata.
        """
        from backend.app.models.workspace.enums import LaunchStatus

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=ttl_hours)

        return {
            "workspace_id": workspace_id,
            "launch_status": LaunchStatus.EPHEMERAL.value,
            "ttl_hours": ttl_hours,
            "expires_at": expires_at.isoformat(),
            "parent_workspace_id": parent_workspace_id,
        }

    def collect_expired(
        self,
        all_workspaces: List[Dict[str, Any]],
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Find ephemeral workspaces that have exceeded their TTL.

        Args:
            all_workspaces: List of workspace dicts with launch_status/expires_at.
            now: Current time (defaults to utcnow).

        Returns:
            List of expired workspace dicts.
        """
        from backend.app.models.workspace.enums import LaunchStatus

        now = now or datetime.now(timezone.utc)
        expired = []

        for ws in all_workspaces:
            if ws.get("launch_status") != LaunchStatus.EPHEMERAL.value:
                continue
            expires_at_raw = ws.get("expires_at")
            if not expires_at_raw:
                continue
            if isinstance(expires_at_raw, str):
                expires_at = datetime.fromisoformat(expires_at_raw)
            else:
                expires_at = expires_at_raw
            # Ensure timezone-aware comparison
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now >= expires_at:
                expired.append(ws)

        return expired

    def transfer_assets(
        self,
        source_workspace_id: str,
        target_workspace_id: str,
        asset_ids: Optional[List[str]] = None,
    ) -> AssetTransferResult:
        """Transfer asset bindings from source (ephemeral) to target (parent).

        Steps:
        1. List ASSET bindings in source workspace
        2. Create or update bindings in target workspace
        3. Remove bindings from source

        Args:
            source_workspace_id: Ephemeral workspace being torn down.
            target_workspace_id: Parent workspace receiving assets.
            asset_ids: Optional filter — only transfer these asset IDs.

        Returns:
            AssetTransferResult with transfer details.
        """
        from backend.app.models.workspace_resource_binding import ResourceType

        result = AssetTransferResult(
            source_workspace_id=source_workspace_id,
            target_workspace_id=target_workspace_id,
        )

        try:
            bindings = self.binding_store.list_bindings_by_workspace(
                source_workspace_id, resource_type=ResourceType.ASSET
            )

            for binding in bindings:
                if asset_ids and binding.resource_id not in asset_ids:
                    continue
                try:
                    self.binding_store.create_or_update_binding(
                        workspace_id=target_workspace_id,
                        resource_type=ResourceType.ASSET,
                        resource_id=binding.resource_id,
                        overrides=binding.overrides,
                    )
                    result.transferred.append(binding.resource_id)
                except Exception as exc:
                    logger.warning(
                        "Failed to transfer asset %s: %s",
                        binding.resource_id,
                        exc,
                    )
                    result.failed.append(
                        {
                            "resource_id": binding.resource_id,
                            "error": str(exc),
                        }
                    )

            result.status = (
                "ok"
                if not result.failed
                else "partial" if result.transferred else "failed"
            )
        except Exception as exc:
            logger.error(
                "Asset transfer failed %s → %s: %s",
                source_workspace_id,
                target_workspace_id,
                exc,
            )
            result.status = "error"

        return result

    def teardown_workspace(self, workspace_id: str) -> Dict[str, Any]:
        """Execute full teardown sequence for an ephemeral workspace.

        Steps:
        1. Transfer assets to parent workspace (if parent exists)
        2. Mark workspace as TEARDOWN status
        3. Return summary

        Args:
            workspace_id: Ephemeral workspace to tear down.

        Returns:
            Teardown result summary.
        """
        from backend.app.models.workspace.enums import LaunchStatus

        ws = self.workspace_store.get_workspace_sync(workspace_id)
        if not ws:
            return {
                "workspace_id": workspace_id,
                "status": "not_found",
            }

        ws_dict = ws.model_dump() if hasattr(ws, "model_dump") else ws
        parent_id = ws_dict.get("parent_workspace_id")

        transfer_result = None
        if parent_id:
            transfer_result = self.transfer_assets(workspace_id, parent_id)

        return {
            "workspace_id": workspace_id,
            "parent_workspace_id": parent_id,
            "launch_status": LaunchStatus.TEARDOWN.value,
            "transfer": (
                {
                    "transferred": transfer_result.transferred,
                    "failed": transfer_result.failed,
                    "status": transfer_result.status,
                }
                if transfer_result
                else None
            ),
        }

    # ── Async wrappers (PF-3) ──────────────────────────────────

    async def mark_ephemeral_async(
        self,
        workspace_id: str,
        ttl_hours: int = 24,
        parent_workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Async wrapper for mark_ephemeral."""
        return await asyncio.to_thread(
            self.mark_ephemeral, workspace_id, ttl_hours, parent_workspace_id
        )

    async def collect_expired_async(
        self,
        all_workspaces: List[Dict[str, Any]],
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Async wrapper for collect_expired."""
        return await asyncio.to_thread(self.collect_expired, all_workspaces, now)

    async def transfer_assets_async(
        self,
        source_workspace_id: str,
        target_workspace_id: str,
        asset_ids: Optional[List[str]] = None,
    ) -> AssetTransferResult:
        """Async wrapper for transfer_assets."""
        return await asyncio.to_thread(
            self.transfer_assets, source_workspace_id, target_workspace_id, asset_ids
        )

    async def teardown_workspace_async(self, workspace_id: str) -> Dict[str, Any]:
        """Async wrapper for teardown_workspace."""
        return await asyncio.to_thread(self.teardown_workspace, workspace_id)
