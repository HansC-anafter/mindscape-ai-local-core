"""
Effective Lens Resolver for three-layer stacking.

Resolves effective lens by merging:
1. Global Preset (lens_profile_nodes)
2. Workspace Override (workspace_lens_overrides)
3. Session Override (session_override_store)
"""
from typing import Optional, Dict, Literal
from datetime import datetime, timezone

from app.services.stores.graph_store import GraphStore
from app.services.lens.session_override_store import SessionOverrideStore
from app.models.graph import GraphNode, LensNodeState
from app.models.lens_kernel import (
    EffectiveLens, LensNode, compute_lens_hash
)


class EffectiveLensResolver:
    """Resolve effective lens from three-layer stacking"""

    def __init__(
        self,
        graph_store: GraphStore,
        session_store: SessionOverrideStore
    ):
        self.graph_store = graph_store
        self.session_store = session_store

    def resolve(
        self,
        profile_id: str,
        workspace_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> EffectiveLens:
        """
        Resolve effective lens

        Args:
            profile_id: User profile ID
            workspace_id: Optional workspace ID
            session_id: Optional session ID

        Returns:
            EffectiveLens with three-layer merged nodes
        """
        all_nodes = self.graph_store.list_nodes(profile_id=profile_id, is_active=True, limit=10000)

        global_preset = self.graph_store.get_active_lens(profile_id, workspace_id)
        if not global_preset:
            raise ValueError(f"No active lens found for profile {profile_id}")

        global_profile_nodes = self.graph_store.get_lens_profile_nodes(global_preset.id)
        global_states: Dict[str, LensNodeState] = {
            pn.node_id: pn.state for pn in global_profile_nodes
        }

        workspace_states: Dict[str, LensNodeState] = {}
        if workspace_id:
            workspace_override = self.graph_store.get_workspace_override(workspace_id)
            if workspace_override:
                workspace_states = workspace_override

        session_states: Dict[str, LensNodeState] = {}
        if session_id:
            session_override = self.session_store.get(session_id)
            if session_override:
                session_states = session_override

        effective_nodes = []
        ws_override_count = 0
        session_override_count = 0

        for node in all_nodes:
            result = self._merge_node_state(
                node,
                global_states.get(node.id),
                workspace_states.get(node.id),
                session_states.get(node.id)
            )
            effective_nodes.append(result)

            if result.overridden_from == "global" and result.effective_scope == "workspace":
                ws_override_count += 1
            if result.effective_scope == "session":
                session_override_count += 1

        lens_hash = compute_lens_hash(effective_nodes)

        return EffectiveLens(
            profile_id=profile_id,
            workspace_id=workspace_id,
            session_id=session_id,
            nodes=effective_nodes,
            global_preset_id=global_preset.id,
            global_preset_name=global_preset.name,
            workspace_override_count=ws_override_count,
            session_override_count=session_override_count,
            hash=lens_hash,
            computed_at=datetime.now(timezone.utc)
        )

    def _merge_node_state(
        self,
        node: GraphNode,
        global_state: Optional[LensNodeState],
        workspace_state: Optional[LensNodeState],
        session_state: Optional[LensNodeState]
    ) -> LensNode:
        """Merge single node's three-layer state"""

        state = global_state or LensNodeState.KEEP
        effective_scope: Literal["global", "workspace", "session"] = "global"
        is_overridden = False
        overridden_from: Optional[Literal["global", "workspace"]] = None

        if workspace_state is not None:
            state = workspace_state
            effective_scope = "workspace"
            is_overridden = True
            overridden_from = "global"

        if session_state is not None:
            overridden_from = effective_scope
            state = session_state
            effective_scope = "session"
            is_overridden = True

        return LensNode(
            node_id=node.id,
            node_label=node.label,
            node_type=node.node_type,
            category=node.category,
            state=state,
            effective_scope=effective_scope,
            is_overridden=is_overridden,
            overridden_from=overridden_from
        )

