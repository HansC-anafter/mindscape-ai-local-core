"""Payload builders for the PD real IG storyboard E2E."""

from __future__ import annotations

import argparse
from typing import Any


def _build_start_body(args: argparse.Namespace, run_id: str) -> dict[str, Any]:
    return {
        "workspace_id": args.workspace_id,
        "project_id": args.project_id,
        "thread_id": args.thread_id or f"thread_e2e_pd_real_ig_{run_id.lower()}",
        "lens_id": args.lens_id,
        "meeting_type": "e2e_validation",
        "agenda": [
            "Run PD real IG 90s storyboard E2E with workspace codex_cli, IG reference validation, and content gate evidence"
        ],
        "success_criteria": [
            "workspace codex_cli bridge connected",
            "IG refs validation checklist passes",
            "45 numbered scenes",
            "total duration about 90 seconds",
            "source-backed IG reference cue map",
            "per-scene runtime LLM judge pass",
            "no internal workflow copy",
            "storyboard assets collected in one directory",
        ],
        "max_rounds": args.max_rounds,
    }


def _quality_requirements(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "rewrite_until_quality_passed": True,
        "reference_grounding_required": True,
        "audience_facing_script_required": True,
        "reject_vague_scene_copy": True,
        "per_scene_content_specificity": "high",
        "deliverable_stage": "storyboard_review",
        "creative_objective": "source_backed_vertical_reels_storyboard",
        "originality_required": True,
        "human_review_required_before_publish": True,
        "target": {
            "deliverable_kind": "90s_reels_storyboard",
            "scene_count_target": args.scene_count_target,
            "scene_count_floor": args.scene_count_floor,
            "total_duration_sec": args.target_duration_sec,
            "scene_count": args.scene_count_target,
            "min_scene_count": args.scene_count_floor,
            "duration_sec": args.target_duration_sec,
            "visual_scope": "storyboard_frames",
            "target_platform": "instagram_reels",
        },
        "content_quality": {
            "require_reference_grounding": True,
            "require_concrete_scene_copy": True,
            "require_per_scene_judge": True,
            "reject_internal_workflow_copy": True,
            "reject_generic_filler": True,
        },
        "visual_quality": {
            "require_storyboard_frames": True,
            "require_contact_sheet": True,
        },
    }


def _build_envelope(
    args: argparse.Namespace,
    *,
    meeting_id: str,
    run_id: str,
    command_id: str,
    ref_ids: list[str],
) -> dict[str, Any]:
    human_instructions = (
        "Create a source-backed 90 second vertical Instagram Reels storyboard from "
        "the selected rin.215_ IG references. Produce 45 numbered scenes at about "
        "2 seconds per scene, with concrete shot-by-shot visual action, screen text, "
        "voiceover, reference grounding, pacing, brand tone, and CTA logic. Do not "
        "use synthetic references or internal workflow copy."
    )
    quality_requirements = _quality_requirements(args)
    input_params = {
        "project_id": args.project_id,
        "source_type": "generative",
        "selected_reference_ids": ref_ids,
        "reference_ids": ref_ids,
        "target_duration_sec": args.target_duration_sec,
        "scene_count_target": args.scene_count_target,
        "scene_count_floor": args.scene_count_floor,
        "raw_intent_text": human_instructions,
        "e2e_run_id": run_id,
        "quality_requirements": quality_requirements,
        "human_instructions": human_instructions,
    }
    return {
        "workspace_id": args.workspace_id,
        "meeting_id": meeting_id,
        "command_id": command_id,
        "origin_surface": "meeting_workbench",
        "actor": "user",
        "intent_text": human_instructions,
        "context_objects": [
            {
                "role": "source",
                "ref": {
                    "uri": f"mindscape://ig/reference/{ref_id}",
                    "owner_pack": "ig",
                    "object_kind": "reference",
                    "object_id": ref_id,
                    "workspace_id": args.workspace_id,
                },
            }
            for ref_id in ref_ids
        ],
        "requested_action": {
            "verb": "execute_playbook",
            "pack_code": "performance_direction",
            "playbook_code": "pd_storyboard_gen",
            "parameters": dict(input_params),
        },
        "expected_outputs": [
            "pd_storyboard_manifest",
            "pd_reference_cue_map",
            "pd_storyboard_quality_gate",
            "pd_storyboard_scene_judge",
            "pd_storyboard_instruction_contract",
            "pd_storyboard_contact_sheet",
        ],
        "write_mode": "proposal_only",
        "metadata": {
            "dispatch_mode": "route_meeting_orchestration",
            "force_playbook_request": False,
            "explicit_override": False,
            "meeting_orchestration_timeout_seconds": args.command_timeout_seconds,
            "raw_intent_text": human_instructions,
            "selected_reference_ids": ref_ids,
            "e2e_run_id": run_id,
            "quality_requirements": quality_requirements,
            "action_parameters": {
                "project_id": args.project_id,
                "source_type": "generative",
                "selected_reference_ids": ref_ids,
                "reference_ids": ref_ids,
                "target_duration_sec": args.target_duration_sec,
                "scene_count_target": args.scene_count_target,
                "scene_count_floor": args.scene_count_floor,
                "e2e_run_id": run_id,
            },
        },
        "thread_id": args.thread_id or f"thread_e2e_pd_real_ig_{run_id.lower()}",
    }
