"""
ChangeSet Service for Mind-Lens unified implementation.

Handles server-side diff and changeset application.
"""
import uuid
import logging
from typing import List, Optional, Dict
from datetime import datetime, timezone

from app.services.stores.graph_store import GraphStore
from app.services.lens.effective_lens_resolver import EffectiveLensResolver
from app.services.lens.session_override_store import SessionOverrideStore
from app.models.changeset import ChangeSet, NodeChange
from app.models.graph import LensNodeState
from app.models.lens_kernel import EffectiveLens
import os

logger = logging.getLogger(__name__)


class ChangeSetService:
    """Service for managing changesets"""

    def __init__(
        self,
        graph_store: GraphStore,
        resolver: EffectiveLensResolver,
        session_store: SessionOverrideStore
    ):
        self.graph_store = graph_store
        self.resolver = resolver
        self.session_store = session_store

    def create_changeset(
        self,
        profile_id: str,
        session_id: str,
        workspace_id: Optional[str] = None
    ) -> ChangeSet:
        """
        Create changeset with server-side diff

        Strategy:
        1. Get baseline = Global Preset ⊕ Workspace Override (not just Global)
        2. Get session overrides
        3. Diff (session vs baseline) → changes[]
        4. Return ChangeSet (not stored, client carries)
        """
        baseline = self.resolver.resolve(
            profile_id=profile_id,
            workspace_id=workspace_id,
            session_id=None
        )

        current = self.resolver.resolve(
            profile_id=profile_id,
            workspace_id=workspace_id,
            session_id=session_id
        )

        baseline_map = {n.node_id: n.state for n in baseline.nodes}
        current_map = {n.node_id: n.state for n in current.nodes}

        changes = []
        for node_id, current_node in current_map.items():
            baseline_state = baseline_map.get(node_id)
            if baseline_state and baseline_state != current_node:
                node_label = next(
                    (n.node_label for n in current.nodes if n.node_id == node_id),
                    node_id
                )
                changes.append(NodeChange(
                    node_id=node_id,
                    node_label=node_label,
                    from_state=baseline_state,
                    to_state=current_node
                ))

        summary = self._generate_summary(changes)

        return ChangeSet(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
            session_id=session_id,
            workspace_id=workspace_id,
            changes=changes,
            summary=summary,
            created_at=datetime.now(timezone.utc)
        )

    def apply_changeset(
        self,
        changeset: ChangeSet,
        apply_to: str,
        target_workspace_id: Optional[str] = None
    ) -> bool:
        """
        Apply changeset to target scope

        Args:
            changeset: ChangeSet to apply (carried by client)
            apply_to: Apply target (session_only, workspace, preset)
            target_workspace_id: Optional target workspace ID

        Returns:
            True if successful
        """
        if apply_to == "session_only":
            return True

        elif apply_to == "workspace":
            ws_id = target_workspace_id or changeset.workspace_id
            if not ws_id:
                raise ValueError("workspace_id required for workspace apply")

            for change in changeset.changes:
                self.graph_store.set_workspace_override(
                    workspace_id=ws_id,
                    node_id=change.node_id,
                    state=change.to_state
                )
            return True

        elif apply_to == "preset":
            active_preset = self.graph_store.get_active_lens(
                changeset.profile_id,
                changeset.workspace_id
            )
            if not active_preset:
                raise ValueError(f"No active preset found for profile {changeset.profile_id}")

            for change in changeset.changes:
                self.graph_store.upsert_lens_profile_node(
                    preset_id=active_preset.id,
                    node_id=change.node_id,
                    state=change.to_state
                )
            return True

        else:
            raise ValueError(f"Unknown apply_to: {apply_to}")

    def _generate_summary(self, changes: List[NodeChange]) -> str:
        """Generate human-readable summary"""
        emphasized = [
            c.node_label for c in changes
            if c.to_state == LensNodeState.EMPHASIZE
        ]
        weakened = [
            c.node_label for c in changes
            if c.to_state == LensNodeState.KEEP and c.from_state == LensNodeState.EMPHASIZE
        ]
        disabled = [
            c.node_label for c in changes
            if c.to_state == LensNodeState.OFF
        ]

        parts = []
        if emphasized:
            parts.append(f"強化了「{', '.join(emphasized)}」")
        if weakened:
            parts.append(f"弱化了「{', '.join(weakened)}」")
        if disabled:
            parts.append(f"關閉了「{', '.join(disabled)}」")

        return "；".join(parts) if parts else "無變更"

