"""Single Meeting session start orchestration behind the HTTP route."""

from __future__ import annotations

import logging
from typing import Any

from backend.app.dependencies.auth import AuthContext
from backend.app.models.meeting_session import MeetingSession
from backend.app.services.meeting_product_admission import admit_meeting_root
from backend.app.services.stores.meeting_session_store import MeetingSessionStore


logger = logging.getLogger(__name__)


class MeetingSessionStartError(RuntimeError):
    def __init__(self, *, status_code: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def _resolve_lens_id(workspace_id: str, requested_lens_id: str | None) -> str | None:
    if requested_lens_id:
        return requested_lens_id
    try:
        from backend.app.services.lens.effective_lens_resolver import (
            EffectiveLensResolver,
        )
        from backend.app.services.lens.session_override_store import (
            InMemorySessionStore,
        )
        from backend.app.services.stores.graph_store import GraphStore

        resolver = EffectiveLensResolver(GraphStore(), InMemorySessionStore())
        effective = resolver.resolve(
            profile_id="default-user",
            workspace_id=workspace_id,
        )
        return effective.global_preset_id
    except Exception as exc:
        logger.warning(
            "[MeetingSession] Failed to resolve lens_id for session: %s",
            exc,
        )
        return None


async def start_meeting_session(
    *,
    workspace_id: str,
    body: Any,
    header_group_id: str | None,
    remote_ingress_verified: bool,
    trace_id: str | None,
    auth: AuthContext,
) -> dict[str, Any]:
    if (
        body.active_group_id
        and header_group_id
        and body.active_group_id != header_group_id
    ):
        raise MeetingSessionStartError(
            status_code=400,
            detail="active group header/body mismatch",
        )
    active_group_id = body.active_group_id or header_group_id
    if not active_group_id and body.expected_topology_snapshot_id:
        raise MeetingSessionStartError(
            status_code=422,
            detail="expected_topology_snapshot_requires_active_group",
        )

    session = MeetingSession.new(
        workspace_id=workspace_id,
        project_id=body.project_id,
        thread_id=body.thread_id,
        meeting_type=body.meeting_type,
        agenda=body.agenda,
        success_criteria=body.success_criteria,
        max_rounds=body.max_rounds or 5,
    )
    selector_key = body.product_selector_key or (
        f"/api/v1/workspaces/{workspace_id}/meeting-sessions/start"
    )
    admission = await admit_meeting_root(
        workspace_id=workspace_id,
        active_group_id=active_group_id,
        observed_topology_revision=body.observed_topology_revision,
        product_surface_id=body.product_surface_id,
        selector_kind=body.product_selector_kind,
        selector_key=selector_key,
        operation_type=body.operation_type,
        execution_backend=body.execution_backend,
        remote_ingress_verified=remote_ingress_verified,
        auth=auth,
        trace_id=trace_id or session.id,
        root_execution_id=session.id,
    )

    group_context = admission.active_group_context
    group_snapshot = admission.topology_snapshot
    if (
        body.expected_topology_snapshot_id
        and (
            group_snapshot is None
            or group_snapshot.id != body.expected_topology_snapshot_id
        )
    ):
        raise MeetingSessionStartError(
            status_code=409,
            detail="workspace_group_snapshot_stale",
        )

    session.lens_id = _resolve_lens_id(workspace_id, body.lens_id)
    session.workspace_group_snapshot_id = (
        group_snapshot.id if group_snapshot else None
    )
    session.metadata.update(body.metadata or {})
    session.metadata.update(
        {
            "execution_admission_snapshot": admission.snapshot.model_dump(
                mode="json"
            ),
            "root_execution_id": session.id,
            "product_surface_id": admission.snapshot.product_surface_id,
        }
    )
    if group_context:
        session.metadata.update(
            {
                "active_group_id": group_context.group_id,
                "workspace_group_revision": group_context.revision,
                "workspace_group_role": group_context.role,
                "workspace_group_snapshot": group_snapshot.model_dump(
                    mode="json"
                ),
            }
        )

    store = MeetingSessionStore()
    existing = store.get_active_session(
        workspace_id,
        body.project_id,
        body.thread_id,
    )
    if existing:
        store.end_session(existing.id)
        logger.info(
            "[MeetingSession] Ended previous session %s before starting new one",
            existing.id,
        )
    session.start()
    store.create(session)
    logger.info("[MeetingSession] Started session %s", session.id)
    return session.to_dict()
