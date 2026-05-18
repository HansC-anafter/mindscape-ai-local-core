"""Workspace metadata writeback helpers for meeting sessions."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MeetingSessionWorkspaceMetadataMixin:
    def _schedule_workspace_update(self, workspace: Any) -> None:
        update_workspace = getattr(getattr(self, "store", None), "update_workspace", None)
        if not callable(update_workspace):
            return

        async def _persist() -> None:
            try:
                await update_workspace(workspace)
            except Exception as exc:
                logger.warning(
                    "Failed to persist workspace capability metadata updates for %s: %s",
                    getattr(workspace, "id", "unknown"),
                    exc,
                )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_persist())
            return

        loop.create_task(_persist())

    def _writeback_capability_metadata_updates_to_workspace(self) -> None:
        updates = self.session.metadata.get("capability_workspace_metadata_updates")
        workspace = getattr(self, "workspace", None)
        if not isinstance(updates, dict) or not updates or workspace is None:
            return

        if getattr(workspace, "metadata", None) is None:
            workspace.metadata = {}

        applied_keys: list[str] = []
        for key, value in updates.items():
            if not key or value in (None, "", [], {}):
                continue
            workspace.metadata[str(key)] = value
            applied_keys.append(str(key))

        self.session.metadata["capability_workspace_metadata_writeback"] = {
            "status": "applied",
            "keys": applied_keys,
        }
        if applied_keys:
            self._schedule_workspace_update(workspace)
