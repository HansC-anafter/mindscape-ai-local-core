"""Performance Direction compile request helpers for acceptance."""

from __future__ import annotations

from typing import Any

from pd_ux_aol_acceptance_common import _json_post


def _compile_director_guidance(
    api_url: str,
    workspace_id: str,
    scene_id: str,
    object_ref: dict[str, Any],
    graph_projection: dict[str, Any],
) -> dict[str, Any]:
    return _json_post(
        f"{api_url}/api/v1/capabilities/performance_direction/director-guidance-compile",
        {
            "workspace_id": workspace_id,
            "scene_id": scene_id,
            "creator_intent": "AOL meeting director guidance acceptance",
            "decision_question": "Which visual direction should be reviewed?",
            "selected_scene": {
                "scene_id": scene_id,
                "title": "Acceptance scene",
                "reference_ids": ["ref_attachbac001"],
            },
            "context_objects": [{"role": "target", "ref": object_ref}],
            "graph_projection": graph_projection,
            "metadata": {"acceptance_stage": "S4-S6"},
        },
        timeout=45.0,
    )


def _compile_runtime_readiness(
    api_url: str,
    workspace_id: str,
    scene_id: str,
) -> dict[str, Any]:
    return _json_post(
        f"{api_url}/api/v1/capabilities/performance_direction/runtime-readiness-check",
        {
            "workspace_id": workspace_id,
            "selected_scene": {
                "scene_id": scene_id,
                "title": "Acceptance scene",
                "reference_ids": ["ref_attachbac001"],
                "duration_sec": 6,
            },
            "provider_readiness": {
                "providers": [
                    {
                        "provider": "local_preview",
                        "available": True,
                        "cost_estimate": {"workstation_minutes": 2},
                    }
                ]
            },
            "preferred_route": "local_preview",
            "metadata": {"acceptance_stage": "S7"},
        },
        timeout=45.0,
    )


def _compile_scene_critique(
    api_url: str,
    workspace_id: str,
    scene_id: str,
    object_ref: dict[str, Any],
    readiness_check: dict[str, Any],
) -> dict[str, Any]:
    return _json_post(
        f"{api_url}/api/v1/capabilities/performance_direction/scene-critique",
        {
            "workspace_id": workspace_id,
            "selected_scene": {
                "scene_id": scene_id,
                "title": "Acceptance scene",
                "reference_ids": ["ref_attachbac001"],
            },
            "runtime_readiness_check": readiness_check,
            "preview_run_summary": {
                "status": "review_required",
                "run_id": "acceptance_preview",
                "metrics": {"frame_count": 1},
            },
            "scene_result_refs": [
                {
                    "owner_pack": object_ref["owner_pack"],
                    "object_kind": object_ref["object_kind"],
                    "object_id": object_ref["object_id"],
                }
            ],
            "metadata": {"acceptance_stage": "S7"},
        },
        timeout=45.0,
    )


def _compile_human_contribution(
    api_url: str,
    workspace_id: str,
    scene_id: str,
) -> dict[str, Any]:
    return _json_post(
        f"{api_url}/api/v1/capabilities/performance_direction/human-contribution-compile",
        {
            "workspace_id": workspace_id,
            "scene_id": scene_id,
            "creator_intent": "Use governed human contribution evidence for director choice",
            "selected_scene": {"scene_id": scene_id, "title": "Acceptance scene"},
            "human_contributions": [
                {
                    "contribution_id": "pdhc_acceptance_actor_take",
                    "contributor_role": "actor",
                    "contribution_type": "performance_take",
                    "role": "evidence",
                    "owner_pack": "local-core",
                    "object_kind": "performance_capture",
                    "object_id": "capture_acceptance_001",
                    "purpose": "Actor handoff timing evidence for selected scene",
                    "decision_relevance": ["performance_anchor_for_cast_direction"],
                    "source_owner": "local-core",
                    "privacy_scope": "local_private",
                    "provenance": {
                        "source_owner": "local-core",
                        "capture_ref": "capture_acceptance_001",
                    },
                    "consent_scope": {
                        "project_only": True,
                        "reusable": False,
                        "consent_ref": "consent_acceptance_001",
                        "allowed_uses": ["director_review"],
                    },
                    "usage_scope": {
                        "reusable_recipe": False,
                        "derivative_allowed": False,
                        "allowed_contexts": ["workspace_review"],
                        "retention_policy": "owner_pack_only",
                    },
                    "bounded_projection": {"timing_note": "handoff starts on count three"},
                }
            ],
            "preferred_route": "local_capture",
            "provider_readiness": {"provider_code": "local_capture", "blockers": []},
            "metadata": {"acceptance_stage": "S8"},
        },
        timeout=45.0,
    )
