from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import backend.app as backend_app

sys.modules["app"] = backend_app

from backend.app.models.meeting_session import MeetingSession
from backend.app.models.object_runtime import ObjectMeetingAttachRequest, ObjectRef
from backend.app.services.object_catalog_registry import ObjectCatalogRegistry


def _load_object_runtime_module():
    workspace_dir = REPO_ROOT / "backend" / "app" / "routes" / "core" / "workspace"
    package_name = "backend.app.routes.core.workspace"
    if package_name not in sys.modules:
        workspace_package = types.ModuleType(package_name)
        workspace_package.__path__ = [str(workspace_dir)]
        sys.modules[package_name] = workspace_package

    module_path = workspace_dir / "object_runtime.py"
    module_name = "backend.app.routes.core.workspace.object_runtime_attach_test_module"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    loaded_module = importlib.util.module_from_spec(spec)
    loaded_module.__package__ = package_name
    spec.loader.exec_module(loaded_module)
    return loaded_module


module = _load_object_runtime_module()


class StubWorkspaceStore:
    async def get_workspace(self, workspace_id: str):
        return SimpleNamespace(id=workspace_id)


class StubMeetingSessionStore:
    def __init__(self, existing: MeetingSession | None = None):
        self.created: list[MeetingSession] = []
        self.updated: list[MeetingSession] = []
        self.by_id = {}
        if existing is not None:
            self.by_id[existing.id] = existing

    def get_by_id(self, session_id: str):
        return self.by_id.get(session_id)

    def create(self, session: MeetingSession):
        self.by_id[session.id] = session
        self.created.append(session)
        return session

    def update(self, session: MeetingSession):
        self.by_id[session.id] = session
        self.updated.append(session)
        return session


class ASGIAsyncTestClient:
    def __init__(self, app):
        self.app = app
        self.base_url = "http://testserver"

    def request(self, method, url, **kwargs):
        async def _request():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_request())

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1/workspaces")
    return app


def _seed_registry(
    tmp_path: Path,
    *,
    include_source_projection: bool = True,
    include_source_summary: bool = True,
):
    registry = ObjectCatalogRegistry(tmp_path)
    registry.sync_pack_objects(
        "ig",
        {
            "object_exports": [
                {
                    "kind": "reference",
                    "display_name": "IG Reference",
                    "id_field": "reference_id",
                    "supports": ["summary", "meeting_projection"],
                }
            ],
            "meeting_projections": (
                [
                    {
                        "kind": "reference",
                        "projection_backend": (
                            "capabilities.ig.object_layer.reference_resolver:build_meeting_projection"
                        ),
                        "verbs": ["attach", "recommend"],
                    }
                ]
                if include_source_projection
                else []
            ),
            "object_resolvers": (
                [
                    {
                        "kind": "reference",
                        "summary_backend": (
                            "capabilities.ig.object_layer.reference_resolver:resolve_summary"
                        ),
                    }
                ]
                if include_source_summary
                else []
            ),
        },
    )
    registry.sync_pack_objects(
        "performance_direction",
        {
            "object_exports": [
                {
                    "kind": "storyboard_scene",
                    "display_name": "Storyboard Scene",
                    "id_field": "scene_id",
                    "supports": ["summary", "materializer"],
                }
            ],
            "materializers": [
                {
                    "kind": "storyboard_scene",
                    "backend": (
                        "capabilities.performance_direction.object_layer.storyboard_materializer:materialize"
                    ),
                    "verbs": ["stage", "review"],
                    "output_types": ["proposal_artifact"],
                    "write_mode": "proposal_only",
                }
            ],
        },
    )
    registry.sync_pack_objects(
        "public_persona_studio",
        {
            "object_exports": [
                {
                    "kind": "foundation_snapshot",
                    "display_name": "PPS Foundation Snapshot",
                    "id_field": "artifact_id",
                    "supports": ["summary", "meeting_projection"],
                },
                {
                    "kind": "pd_workflow_handoff",
                    "display_name": "PPS PD Workflow Handoff",
                    "id_field": "handoff_id",
                    "supports": ["summary", "meeting_projection"],
                },
            ],
            "object_resolvers": [
                {
                    "kind": "foundation_snapshot",
                    "summary_backend": (
                        "capabilities.public_persona_studio.services.object_layer.foundation_snapshot_runtime:resolve_foundation_snapshot_summary"
                    ),
                },
                {
                    "kind": "pd_workflow_handoff",
                    "summary_backend": (
                        "capabilities.public_persona_studio.services.object_layer.pd_workflow_handoff_runtime:resolve_pd_workflow_handoff_summary"
                    ),
                },
            ],
            "meeting_projections": [
                {
                    "kind": "foundation_snapshot",
                    "projection_backend": (
                        "capabilities.public_persona_studio.services.object_layer.foundation_snapshot_runtime:project_foundation_snapshot_for_meeting"
                    ),
                    "verbs": ["attach", "preview"],
                },
                {
                    "kind": "pd_workflow_handoff",
                    "projection_backend": (
                        "capabilities.public_persona_studio.services.object_layer.pd_workflow_handoff_runtime:project_pd_workflow_handoff_for_meeting"
                    ),
                    "verbs": ["attach", "preview"],
                },
            ],
        },
    )
    return registry


async def _fake_scenario_3_invoke_backend_callable(backend_path, **kwargs):
    assert kwargs["workspace_id"] == "ws_demo"
    object_id = kwargs["object_id"]

    if backend_path == (
        "capabilities.public_persona_studio.services.object_layer.foundation_snapshot_runtime:resolve_foundation_snapshot_summary"
    ):
        return {
            "artifact_id": object_id,
            "display_label": "PPS Foundation Snapshot",
            "summary_text": "Brand baseline with governance constraints.",
            "owner_surface_url": "/api/v1/capabilities/public_persona_studio/workbench/state?workspace_id=ws_demo",
        }
    if backend_path == (
        "capabilities.public_persona_studio.services.object_layer.foundation_snapshot_runtime:project_foundation_snapshot_for_meeting"
    ):
        return {
            "verb": "attach",
            "title": "PPS Foundation Snapshot",
            "summary_text": "Brand baseline with governance constraints.",
            "object_context": {
                "artifact_id": object_id,
                "foundation_mode": "brand_foundation",
                "memory_scope": "workspace",
            },
            "preview": {
                "owner_surface_url": "/api/v1/capabilities/public_persona_studio/workbench/state?workspace_id=ws_demo"
            },
        }
    if backend_path == (
        "capabilities.public_persona_studio.services.object_layer.pd_workflow_handoff_runtime:resolve_pd_workflow_handoff_summary"
    ):
        return {
            "handoff_id": object_id,
            "display_label": "weekly_beans_drop",
            "summary_text": "PD handoff with scene intent and preview seed.",
            "owner_surface_url": "/api/v1/capabilities/public_persona_studio/workbench/state?workspace_id=ws_demo",
        }
    if backend_path == (
        "capabilities.public_persona_studio.services.object_layer.pd_workflow_handoff_runtime:project_pd_workflow_handoff_for_meeting"
    ):
        return {
            "verb": "attach",
            "title": "weekly_beans_drop",
            "summary_text": "PD handoff with scene intent and preview seed.",
            "object_context": {
                "handoff_id": object_id,
                "scene_intent": "Coffee shelf reveal with editorial pacing.",
                "preview_route_hint": "performance_direction.storyboard_scene",
                "governance_constraints": {
                    "safety_tier": "brand_safe",
                    "avoid": ["graphic violence"],
                },
                "spatial_schedule_artifact_ref": {
                    "owner_pack": "public_persona_studio",
                    "object_kind": "spatial_schedule_artifact",
                    "object_id": "ssa_demo_001",
                },
            },
            "preview": {
                "owner_surface_url": "/api/v1/capabilities/public_persona_studio/workbench/state?workspace_id=ws_demo"
            },
        }
    if backend_path == (
        "capabilities.ig.object_layer.reference_resolver:resolve_summary"
    ):
        return {
            "reference_id": object_id,
            "display_label": f"@demo_handle #{object_id}",
            "source_handle": "@demo_handle",
            "source_shortcode": object_id,
            "analysis_status": "ready",
            "scene_summary": f"Reference summary for {object_id}",
            "owner_surface_url": f"/api/v1/ig/references/{object_id}?workspace_id=ws_demo",
        }
    if backend_path == (
        "capabilities.ig.object_layer.reference_resolver:build_meeting_projection"
    ):
        return {
            "verb": "attach",
            "title": f"@demo_handle #{object_id}",
            "summary_text": f"Reference summary for {object_id}",
            "object_context": {
                "reference_id": object_id,
                "source_handle": "@demo_handle",
            },
            "preview": {
                "image_url": f"/api/v1/ig/references/{object_id}/image?workspace_id=ws_demo"
            },
        }
    if backend_path == (
        "capabilities.performance_direction.object_layer.storyboard_runtime:resolve_storyboard_scene_summary"
    ):
        return {
            "scene_locator_id": object_id,
            "display_label": "Opening shelf reveal",
            "summary_text": "Canonical scene ready for proposal staging.",
            "owner_surface_url": "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard",
        }

    raise AssertionError(f"Unexpected backend path: {backend_path}")


def test_object_meeting_attach_creates_session_and_bounded_attachments(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    meeting_store = StubMeetingSessionStore()
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)

    async def _fake_invoke_backend_callable(backend_path, **kwargs):
        if backend_path == (
            "capabilities.ig.object_layer.reference_resolver:resolve_summary"
        ):
            assert kwargs["workspace_id"] == "ws_demo"
            object_id = kwargs["object_id"]
            return {
                "reference_id": object_id,
                "display_label": f"@demo_handle #{object_id}",
                "source_handle": "@demo_handle",
                "source_shortcode": object_id,
                "analysis_status": "ready",
                "scene_summary": f"Reference summary for {object_id}",
                "image_url": f"/api/v1/ig/references/{object_id}/image?workspace_id=ws_demo",
                "owner_surface_url": f"/api/v1/ig/references/{object_id}?workspace_id=ws_demo",
            }
        assert kwargs["workspace_id"] == "ws_demo"
        assert backend_path == (
            "capabilities.ig.object_layer.reference_resolver:build_meeting_projection"
        )
        object_id = kwargs["object_id"]
        return {
            "verb": "attach",
            "title": f"@demo_handle #{object_id}",
            "summary_text": f"Reference summary for {object_id}",
            "object_context": {
                "reference_id": object_id,
                "source_handle": "@demo_handle",
            },
            "preview": {
                "image_url": f"/api/v1/ig/references/{object_id}/image?workspace_id=ws_demo"
            },
        }

    monkeypatch.setattr(module, "_invoke_backend_callable", _fake_invoke_backend_callable)

    async def _fake_materialize_target_outcome(**kwargs):
        assert kwargs["target_ref"].uri == (
            "mindscape://performance_direction/storyboard_scene/scene_opening_01"
        )
        assert [record.role for record in kwargs["context_records"]] == [
            "source",
            "evidence",
            "target",
        ]
        assert kwargs["context_records"][0].ref.uri == "mindscape://ig/reference/ref_abc123"
        assert kwargs["context_records"][0].meeting_projection["object_context"][
            "reference_id"
        ] == "ref_abc123"
        assert kwargs["context_records"][1].ref.uri == "mindscape://ig/reference/ref_evidence_001"
        return (
            "materialized",
            [
                ObjectRef(
                    uri=(
                        "mindscape://performance_direction/storyboard_proposal_artifact/"
                        "ds_demo_001:da_storyboard_proposal_001"
                    ),
                    owner_pack="performance_direction",
                    object_kind="storyboard_proposal_artifact",
                    object_id="ds_demo_001:da_storyboard_proposal_001",
                    workspace_id="ws_demo",
                )
            ],
            [
                "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/review"
            ],
            [],
            {
                "status": "materialized",
                "staged_ref": {
                    "uri": (
                        "mindscape://performance_direction/storyboard_proposal_artifact/"
                        "ds_demo_001:da_storyboard_proposal_001"
                    ),
                    "owner_pack": "performance_direction",
                    "object_kind": "storyboard_proposal_artifact",
                    "object_id": "ds_demo_001:da_storyboard_proposal_001",
                },
                "review_route": (
                    "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/"
                    "storyboard/proposals/da_storyboard_proposal_001/review"
                ),
            },
        )
    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "direction",
            "meeting_id": None,
            "entries": [
                {
                    "role": "source",
                    "ref": {
                        "uri": "mindscape://ig/reference/ref_abc123",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_abc123",
                        "workspace_id": "ws_demo",
                        "source_surface": "ig.references_grid",
                    },
                },
                {
                    "role": "evidence",
                    "ref": {
                        "uri": "mindscape://ig/reference/ref_evidence_001",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_evidence_001",
                        "workspace_id": "ws_demo",
                        "source_surface": "ig.references_grid",
                    },
                },
                {
                    "role": "target",
                    "ref": {
                        "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
                        "owner_pack": "performance_direction",
                        "object_kind": "storyboard_scene",
                        "object_id": "scene_opening_01",
                        "workspace_id": "ws_demo",
                    },
                },
            ],
            "intent_summary": (
                "Expand this ref into a 5-10s opening beat and stage it for PD review."
            ),
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "ws_demo"
    assert payload["status"] == "materialized"
    assert payload["staged_refs"] == [
        {
            "uri": (
                "mindscape://performance_direction/storyboard_proposal_artifact/"
                "ds_demo_001:da_storyboard_proposal_001"
            ),
            "owner_pack": "performance_direction",
            "object_kind": "storyboard_proposal_artifact",
            "object_id": "ds_demo_001:da_storyboard_proposal_001",
            "workspace_id": "ws_demo",
            "version": None,
            "selector": None,
            "source_surface": None,
        }
    ]
    assert payload["review_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/review"
    ]
    assert [attachment["role"] for attachment in payload["attachments"]] == [
        "source",
        "evidence",
        "target",
    ]
    assert len(meeting_store.created) == 1
    created_session = meeting_store.created[0]
    metadata = created_session.metadata["addressable_object_layer"]
    assert metadata["write_mode"] == "proposal_only"
    assert metadata["status"] == "materialized"
    assert metadata["context_entries"] == [
        {
            "role": "source",
            "ref": {
                "uri": "mindscape://ig/reference/ref_abc123",
                "owner_pack": "ig",
                "object_kind": "reference",
                "object_id": "ref_abc123",
                "workspace_id": "ws_demo",
                "source_surface": "ig.references_grid",
            },
        },
        {
            "role": "evidence",
            "ref": {
                "uri": "mindscape://ig/reference/ref_evidence_001",
                "owner_pack": "ig",
                "object_kind": "reference",
                "object_id": "ref_evidence_001",
                "workspace_id": "ws_demo",
                "source_surface": "ig.references_grid",
            },
        },
        {
            "role": "target",
            "ref": {
                "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
                "owner_pack": "performance_direction",
                "object_kind": "storyboard_scene",
                "object_id": "scene_opening_01",
                "workspace_id": "ws_demo",
            },
        },
    ]
    assert metadata["target_ref"]["uri"] == (
        "mindscape://performance_direction/storyboard_scene/scene_opening_01"
    )
    assert metadata["staged_refs"][0]["object_kind"] == "storyboard_proposal_artifact"
    assert metadata["review_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_001/review"
    ]
    assert metadata["handoff_in"]["workspace_id"] == "ws_demo"
    attachments = metadata["context_attachments"]
    assert len(attachments) == 3
    source_attachment = attachments[0]
    assert source_attachment["object_ref"]["uri"] == "mindscape://ig/reference/ref_abc123"
    assert source_attachment["object_summary"]["title"] == "@demo_handle #ref_abc123"
    assert "canonical_schema" not in source_attachment
    assert "summary_fields" not in source_attachment
    assert source_attachment["meeting_projection"]["payload"] == {
        "verb": "attach",
        "title": "@demo_handle #ref_abc123",
        "summary_text": "Reference summary for ref_abc123",
        "object_context": {
            "reference_id": "ref_abc123",
            "source_handle": "@demo_handle",
        },
        "preview": {
            "image_url": "/api/v1/ig/references/ref_abc123/image?workspace_id=ws_demo"
        },
    }
    evidence_attachment = attachments[1]
    assert evidence_attachment["role"] == "evidence"
    assert evidence_attachment["object_ref"]["uri"] == (
        "mindscape://ig/reference/ref_evidence_001"
    )
    assert evidence_attachment["meeting_projection"]["payload"]["object_context"][
        "reference_id"
    ] == "ref_evidence_001"


def test_object_meeting_attach_preserves_scenario_3_roles_without_target(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    meeting_store = StubMeetingSessionStore()
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)
    monkeypatch.setattr(
        module,
        "_invoke_backend_callable",
        _fake_scenario_3_invoke_backend_callable,
    )

    async def _unexpected_materialize_target_outcome(**kwargs):
        raise AssertionError("target materialization should not run without a target entry")

    monkeypatch.setattr(
        module,
        "_materialize_target_outcome",
        _unexpected_materialize_target_outcome,
    )

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "scenario_3_preflight",
            "entries": [
                {
                    "role": "baseline",
                    "ref": {
                        "uri": "mindscape://public_persona_studio/foundation_snapshot/foundation_001",
                        "owner_pack": "public_persona_studio",
                        "object_kind": "foundation_snapshot",
                        "object_id": "foundation_001",
                        "workspace_id": "ws_demo",
                    },
                },
                {
                    "role": "constraint",
                    "ref": {
                        "uri": "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001",
                        "owner_pack": "public_persona_studio",
                        "object_kind": "pd_workflow_handoff",
                        "object_id": "handoff_001",
                        "workspace_id": "ws_demo",
                    },
                },
                {
                    "role": "evidence",
                    "ref": {
                        "uri": "mindscape://ig/reference/ref_evidence_002",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_evidence_002",
                        "workspace_id": "ws_demo",
                        "source_surface": "ig.references_grid",
                    },
                },
            ],
            "intent_summary": "Attach baseline, constraint, and evidence before target staging.",
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "attached"
    assert payload["staged_refs"] == []
    assert payload["review_routes"] == []
    assert payload["errors"] == []
    assert [attachment["role"] for attachment in payload["attachments"]] == [
        "baseline",
        "constraint",
        "evidence",
    ]

    assert len(meeting_store.created) == 1
    created_session = meeting_store.created[0]
    metadata = created_session.metadata["addressable_object_layer"]
    assert metadata["write_mode"] == "proposal_only"
    assert metadata["status"] == "attached"
    assert metadata["target_ref"] is None
    assert metadata["context_entries"] == [
        {
            "role": "baseline",
            "ref": {
                "uri": "mindscape://public_persona_studio/foundation_snapshot/foundation_001",
                "owner_pack": "public_persona_studio",
                "object_kind": "foundation_snapshot",
                "object_id": "foundation_001",
                "workspace_id": "ws_demo",
            },
        },
        {
            "role": "constraint",
            "ref": {
                "uri": "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001",
                "owner_pack": "public_persona_studio",
                "object_kind": "pd_workflow_handoff",
                "object_id": "handoff_001",
                "workspace_id": "ws_demo",
            },
        },
        {
            "role": "evidence",
            "ref": {
                "uri": "mindscape://ig/reference/ref_evidence_002",
                "owner_pack": "ig",
                "object_kind": "reference",
                "object_id": "ref_evidence_002",
                "workspace_id": "ws_demo",
                "source_surface": "ig.references_grid",
            },
        },
    ]
    handoff_metadata = metadata["handoff_in"]["metadata"]["addressable_object_layer"]
    assert handoff_metadata["role_object_uris"] == {
        "baseline": [
            "mindscape://public_persona_studio/foundation_snapshot/foundation_001"
        ],
        "constraint": [
            "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001"
        ],
        "evidence": ["mindscape://ig/reference/ref_evidence_002"],
    }
    attachments = metadata["context_attachments"]
    assert [attachment["role"] for attachment in attachments] == [
        "baseline",
        "constraint",
        "evidence",
    ]
    assert attachments[0]["meeting_projection"]["payload"]["object_context"] == {
        "artifact_id": "foundation_001",
        "foundation_mode": "brand_foundation",
        "memory_scope": "workspace",
    }
    assert attachments[1]["meeting_projection"]["payload"]["object_context"] == {
        "handoff_id": "handoff_001",
        "scene_intent": "Coffee shelf reveal with editorial pacing.",
        "preview_route_hint": "performance_direction.storyboard_scene",
        "governance_constraints": {
            "safety_tier": "brand_safe",
            "avoid": ["graphic violence"],
        },
        "spatial_schedule_artifact_ref": {
            "owner_pack": "public_persona_studio",
            "object_kind": "spatial_schedule_artifact",
            "object_id": "ssa_demo_001",
        },
    }
    assert attachments[2]["meeting_projection"]["payload"]["object_context"] == {
        "reference_id": "ref_evidence_002",
        "source_handle": "@demo_handle",
    }


def test_object_meeting_attach_materializes_scenario_3_target_bundle(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    meeting_store = StubMeetingSessionStore()
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)
    monkeypatch.setattr(
        module,
        "_invoke_backend_callable",
        _fake_scenario_3_invoke_backend_callable,
    )

    async def _fake_materialize_target_outcome(**kwargs):
        assert kwargs["target_ref"].uri == (
            "mindscape://performance_direction/storyboard_scene/ds_demo_001:da_storyboard_001:sc01"
        )
        assert [record.role for record in kwargs["context_records"]] == [
            "baseline",
            "constraint",
            "evidence",
            "target",
        ]
        return (
            "materialized",
            [
                ObjectRef(
                    uri=(
                        "mindscape://performance_direction/storyboard_proposal_artifact/"
                        "ds_demo_001:da_storyboard_proposal_030"
                    ),
                    owner_pack="performance_direction",
                    object_kind="storyboard_proposal_artifact",
                    object_id="ds_demo_001:da_storyboard_proposal_030",
                    workspace_id="ws_demo",
                )
            ],
            [
                "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_030/review"
            ],
            [],
            {
                "status": "materialized",
                "staged_ref": {
                    "uri": (
                        "mindscape://performance_direction/storyboard_proposal_artifact/"
                        "ds_demo_001:da_storyboard_proposal_030"
                    ),
                    "owner_pack": "performance_direction",
                    "object_kind": "storyboard_proposal_artifact",
                    "object_id": "ds_demo_001:da_storyboard_proposal_030",
                },
                "review_route": (
                    "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/"
                    "storyboard/proposals/da_storyboard_proposal_030/review"
                ),
            },
        )

    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "scenario_3_preflight",
            "entries": [
                {
                    "role": "baseline",
                    "ref": {
                        "uri": "mindscape://public_persona_studio/foundation_snapshot/foundation_001",
                        "owner_pack": "public_persona_studio",
                        "object_kind": "foundation_snapshot",
                        "object_id": "foundation_001",
                        "workspace_id": "ws_demo",
                    },
                },
                {
                    "role": "constraint",
                    "ref": {
                        "uri": "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001",
                        "owner_pack": "public_persona_studio",
                        "object_kind": "pd_workflow_handoff",
                        "object_id": "handoff_001",
                        "workspace_id": "ws_demo",
                    },
                },
                {
                    "role": "evidence",
                    "ref": {
                        "uri": "mindscape://ig/reference/ref_evidence_002",
                        "owner_pack": "ig",
                        "object_kind": "reference",
                        "object_id": "ref_evidence_002",
                        "workspace_id": "ws_demo",
                        "source_surface": "ig.references_grid",
                    },
                },
                {
                    "role": "target",
                    "ref": {
                        "uri": "mindscape://performance_direction/storyboard_scene/ds_demo_001:da_storyboard_001:sc01",
                        "owner_pack": "performance_direction",
                        "object_kind": "storyboard_scene",
                        "object_id": "ds_demo_001:da_storyboard_001:sc01",
                        "workspace_id": "ws_demo",
                    },
                },
            ],
            "intent_summary": "Stage the full Scenario 3 bundle into a PD proposal artifact.",
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "materialized"
    assert [attachment["role"] for attachment in payload["attachments"]] == [
        "baseline",
        "constraint",
        "evidence",
        "target",
    ]
    assert payload["staged_refs"] == [
        {
            "uri": (
                "mindscape://performance_direction/storyboard_proposal_artifact/"
                "ds_demo_001:da_storyboard_proposal_030"
            ),
            "owner_pack": "performance_direction",
            "object_kind": "storyboard_proposal_artifact",
            "object_id": "ds_demo_001:da_storyboard_proposal_030",
            "workspace_id": "ws_demo",
            "version": None,
            "selector": None,
            "source_surface": None,
        }
    ]
    assert payload["review_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_030/review"
    ]

    assert len(meeting_store.created) == 1
    created_session = meeting_store.created[0]
    metadata = created_session.metadata["addressable_object_layer"]
    assert metadata["status"] == "materialized"
    assert metadata["target_ref"] == {
        "uri": "mindscape://performance_direction/storyboard_scene/ds_demo_001:da_storyboard_001:sc01",
        "owner_pack": "performance_direction",
        "object_kind": "storyboard_scene",
        "object_id": "ds_demo_001:da_storyboard_001:sc01",
        "workspace_id": "ws_demo",
    }
    assert metadata["staged_refs"][0]["object_id"] == "ds_demo_001:da_storyboard_proposal_030"
    assert metadata["review_routes"] == [
        "/api/v1/capabilities/performance_direction/sessions/ds_demo_001/storyboard/proposals/da_storyboard_proposal_030/review"
    ]
    assert metadata["materialization_result"]["status"] == "materialized"
    assert metadata["handoff_in"]["metadata"]["addressable_object_layer"]["role_object_uris"] == {
        "baseline": [
            "mindscape://public_persona_studio/foundation_snapshot/foundation_001"
        ],
        "constraint": [
            "mindscape://public_persona_studio/pd_workflow_handoff/handoff_001"
        ],
        "evidence": ["mindscape://ig/reference/ref_evidence_002"],
        "target": [
            "mindscape://performance_direction/storyboard_scene/ds_demo_001:da_storyboard_001:sc01"
        ],
    }


def test_build_session_attachment_metadata_coerces_datetime_materialization_payload():
    request = ObjectMeetingAttachRequest(
        meeting_type="direction",
        objects=[
            ObjectRef(
                uri="mindscape://ig/reference/ref_abc123",
                owner_pack="ig",
                object_kind="reference",
                object_id="ref_abc123",
                workspace_id="ws_demo",
            )
        ],
        intent_summary="Stage attach smoke artifact",
        write_mode="proposal_only",
    )

    metadata = module._build_session_attachment_metadata(
        request=request,
        handoff_payload={
            "context_attachments": [],
            "created_at": datetime(2026, 4, 23, 11, 59, tzinfo=timezone.utc),
        },
        response_status="materialized",
        staged_refs=[],
        review_routes=[],
        materialization_result={
            "status": "materialized",
            "artifact": {
                "artifact_id": "da_storyboard_proposal_001",
                "created_at": datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc),
            },
        },
    )

    assert metadata["materialization_result"] == {
        "status": "materialized",
        "artifact": {
            "artifact_id": "da_storyboard_proposal_001",
            "created_at": "2026-04-23T12:00:00+00:00",
        },
    }
    assert metadata["handoff_in"]["created_at"] == "2026-04-23T11:59:00+00:00"


def test_object_meeting_attach_uses_existing_session(monkeypatch, tmp_path):
    registry = _seed_registry(tmp_path)
    existing = MeetingSession.new(workspace_id="ws_demo", meeting_type="direction")
    existing.start()
    meeting_store = StubMeetingSessionStore(existing=existing)
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)
    async def _fake_materialize_target_outcome(**kwargs):
        return ("attached", [], [], [], None)
    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        f"/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "direction",
            "meeting_id": existing.id,
            "objects": [
                {
                    "uri": "mindscape://ig/reference/ref_abc124",
                    "owner_pack": "ig",
                    "object_kind": "reference",
                    "object_id": "ref_abc124",
                    "workspace_id": "ws_demo",
                }
            ],
            "intent_summary": "Attach another source ref to the open meeting.",
            "write_mode": "recommendation_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meeting_id"] == existing.id
    assert meeting_store.created == []
    assert meeting_store.updated[-1].metadata["addressable_object_layer"][
        "write_mode"
    ] == "recommendation_only"


def test_object_meeting_attach_rejects_missing_meeting_projection(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path, include_source_projection=False)
    meeting_store = StubMeetingSessionStore()
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)
    async def _fake_materialize_target_outcome(**kwargs):
        return ("attached", [], [], [], None)
    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "direction",
            "objects": [
                {
                    "uri": "mindscape://ig/reference/ref_abc125",
                    "owner_pack": "ig",
                    "object_kind": "reference",
                    "object_id": "ref_abc125",
                    "workspace_id": "ws_demo",
                }
            ],
            "intent_summary": "Try attaching a non-projectable object.",
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "projection_unavailable"


def test_object_meeting_attach_rejects_closed_session(monkeypatch, tmp_path):
    registry = _seed_registry(tmp_path)
    closed = MeetingSession.new(workspace_id="ws_demo", meeting_type="direction")
    closed.start()
    closed.close()
    meeting_store = StubMeetingSessionStore(existing=closed)
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)
    async def _fake_materialize_target_outcome(**kwargs):
        return ("attached", [], [], [], None)
    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "direction",
            "meeting_id": closed.id,
            "objects": [
                {
                    "uri": "mindscape://ig/reference/ref_abc126",
                    "owner_pack": "ig",
                    "object_kind": "reference",
                    "object_id": "ref_abc126",
                    "workspace_id": "ws_demo",
                }
            ],
            "intent_summary": "Attach to a closed meeting.",
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "meeting_closed"


def test_object_meeting_attach_returns_rejected_when_materializer_fails(
    monkeypatch, tmp_path
):
    registry = _seed_registry(tmp_path)
    meeting_store = StubMeetingSessionStore()
    monkeypatch.setattr(module, "_get_workspace_store", lambda: StubWorkspaceStore())
    monkeypatch.setattr(module, "_get_object_catalog_registry", lambda: registry)
    monkeypatch.setattr(module, "_get_meeting_session_store", lambda: meeting_store)

    async def _fake_materialize_target_outcome(**kwargs):
        return (
            "rejected",
            [],
            [],
            [
                module.SelectionResolveError(
                    code="materializer_failed",
                    message="Owner-pack materializer failed while staging the attach outcome.",
                )
            ],
            None,
        )

    monkeypatch.setattr(module, "_materialize_target_outcome", _fake_materialize_target_outcome)

    client = ASGIAsyncTestClient(_build_test_app())
    response = client.post(
        "/api/v1/workspaces/ws_demo/object-meeting-attach",
        json={
            "meeting_type": "direction",
            "objects": [
                {
                    "uri": "mindscape://ig/reference/ref_abc129",
                    "owner_pack": "ig",
                    "object_kind": "reference",
                    "object_id": "ref_abc129",
                    "workspace_id": "ws_demo",
                }
            ],
            "target_ref": {
                "uri": "mindscape://performance_direction/storyboard_scene/scene_opening_01",
                "owner_pack": "performance_direction",
                "object_kind": "storyboard_scene",
                "object_id": "scene_opening_01",
                "workspace_id": "ws_demo",
            },
            "intent_summary": "Try staging a PD proposal artifact.",
            "write_mode": "proposal_only",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["staged_refs"] == []
    assert payload["review_routes"] == []
    assert payload["errors"] == [
        {
            "code": "materializer_failed",
            "message": "Owner-pack materializer failed while staging the attach outcome.",
        }
    ]
