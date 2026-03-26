from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from fastapi import FastAPI
import httpx

LOCAL_CORE_ROOT = Path("/Users/shock/Projects_local/workspace/mindscape-ai-local-core")
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
for candidate in (LOCAL_CORE_ROOT, BACKEND_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from backend.app.capabilities.layer_asset_forge.api.layer_asset_forge_endpoints import (
    router,
)


def test_extract_object_assets_route_returns_storyboard_scene_patch(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/capabilities/layer_asset_forge")

    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))

    def _fake_propose_masks(**kwargs):
        assert kwargs["job_id"] == "laf_job_demo"
        return {
            "job": {
                "proposed_masks": [
                    {
                        "object_target_id": "dress_form",
                        "proposal_method": "sam2_bbox_guided",
                        "proposal_status": "ready",
                        "bbox": {"x": 4, "y": 5, "width": 60, "height": 100},
                        "mask_ref": {"storage_key": "laf/masks/dress_form.png"},
                    }
                ],
                "contract": {"schema_version": "object_mask_proposal.v0.1"},
            }
        }

    def _fake_extract_layers(**kwargs):
        targets = kwargs["object_targets"]
        assert targets[0]["mask_ref"] == {"storage_key": "laf/masks/dress_form.png"}
        assert targets[0]["meta"]["mask_proposal_method"] == "sam2_bbox_guided"
        return {
            "job": {
                "contract": {"schema_version": "object_asset_extract.v0.1"},
                "input": {"selection_mode": "targets"},
                "exported_layers": [
                    {
                        "layer_id": "dress_form",
                        "role": "prop",
                        "storage_key": "layer_asset_forge/jobs/laf_job_demo/exports/layers/dress_form.png",
                        "alpha_storage_key": "layer_asset_forge/jobs/laf_job_demo/exports/alpha/dress_form_alpha.png",
                        "mask_storage_key": "layer_asset_forge/jobs/laf_job_demo/exports/masks/dress_form_mask.png",
                        "bbox": {"x": 4, "y": 5, "width": 60, "height": 100},
                        "area_ratio": 0.12,
                        "meta": {
                            "object_target_id": "dress_form",
                            "object_instance_id": "obj_dress_form",
                            "source_reference_fingerprint": "ref_scene_a",
                            "impact_region_mode": "contact_zone",
                            "impact_region_bbox": {
                                "x": 0,
                                "y": 0,
                                "width": 120,
                                "height": 180,
                            },
                            "impact_region_confidence": 0.74,
                            "affected_object_instance_ids": [
                                "obj_dress_form",
                                "obj_person_main",
                            ],
                            "quality_gate_state": "auto_approved",
                            "matte_refinement_status": "applied",
                            "completion_status": "applied",
                        },
                    }
                ],
            }
        }

    monkeypatch.setattr(
        "backend.app.capabilities.layer_asset_forge.api.layer_asset_forge_endpoints.do_propose_masks",
        _fake_propose_masks,
    )
    monkeypatch.setattr(
        "backend.app.capabilities.layer_asset_forge.api.layer_asset_forge_endpoints.do_extract_layers",
        _fake_extract_layers,
    )

    async def _exercise_route():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/capabilities/layer_asset_forge/extract-object-assets",
                json={
                    "job_id": "laf_job_demo",
                    "image_ref": {"storage_key": "refs/source.png"},
                    "selection_mode": "targets",
                    "source_scene_ref": {"scene_id": "SC_PATCH_01"},
                    "object_targets": [
                        {
                            "object_target_id": "dress_form",
                            "label": "Dress Form",
                            "usage_bindings": [
                                {
                                    "scene_id": "A01",
                                    "purpose": "prop",
                                    "placement_policy": "inherit",
                                }
                            ],
                        }
                    ],
                },
            )

    response = asyncio.run(_exercise_route())

    assert response.status_code == 200
    payload = response.json()["job"]
    assert payload["status"] == "completed"
    assert payload["object_asset_refs"][0]["object_instance_id"] == "obj_dress_form"
    assert payload["object_asset_refs"][0]["metadata"]["impact_region_mode"] == "contact_zone"
    assert payload["object_reuse_plan"]["usage_bindings"][0]["scene_id"] == "A01"
    assert payload["object_workload_snapshot"]["source_scene_id"] == "SC_PATCH_01"
    assert payload["object_workload_snapshot"]["source_image_ref"] == {
        "storage_key": "refs/source.png"
    }
    assert payload["object_workload_snapshot"]["impact_region_mode"] == "contact_zone"
    assert payload["object_workload_snapshot"]["quality_gate_state"] == "auto_approved"
    assert payload["storyboard_scene_patch"]["object_assets"][0]["object_target_id"] == "dress_form"
    assert payload["storyboard_scene_patch"]["object_workload_snapshot"]["source_workload_ref"] == "laf_job:laf_job_demo"
