#!/usr/bin/env python3
"""
Deterministic local E2E for the scene-package preview chain.

Flow:
  1. Create a PD session from a real IG reference.
  2. Create a scene generation job using the stub provider.
  3. Advance + poll the job until a scene_package artifact materializes.
  4. Generate a storyboard that replays the scene package.
  5. Execute the storyboard through MMS using local dry-run preview.

This validates the pack-owned chain without requiring a live 3D/world provider.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List


BACKEND_ROOT = Path("/app/backend")
for candidate in (BACKEND_ROOT, BACKEND_ROOT / "app"):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)


DEFAULT_WORKSPACE_ID = "bac7ce63-e768-454d-96f3-3a00e8e1df69"
DEFAULT_REFERENCE_ID = "ref_49690a59"
DEFAULT_REFERENCE_IMAGE_PATH = (
    "/root/.mindscape/workspaces/"
    "bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/"
    "@kachuuu____/CDtaS10pF1o.jpg"
)
DEFAULT_TENANT_ID = "default"


def _require_success(payload: Dict[str, Any], step: str) -> Dict[str, Any]:
    if payload.get("success"):
        return payload
    raise RuntimeError(f"{step} failed: {json.dumps(payload, ensure_ascii=False)}")


def _emit_step(step: str, **payload: Any) -> None:
    event = {"step": step, **payload}
    print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)


def _build_stub_scene_package_payload(
    reference_id: str,
    *,
    canonical_image_ref: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "package_id": f"scene.stub.{reference_id}.v1",
        "provider": "stub",
        "generation_mode": "generated_world",
        "scene_scope": "default",
        "variant_id": "main",
        "status": "generated",
        "source_reference_ids": [reference_id],
        "control_refs": [
            {
                "control_kind": "canonical_image",
                "ref": dict(canonical_image_ref),
                "provider": "stub",
                "metadata": {"origin": "ig_reference"},
            }
        ],
        "spatial_metadata": {
            "coordinate_system": "image_2d",
            "unit_scale": 1.0,
            "up_axis": "Y",
            "forward_axis": "-Z",
            "grounding_mode": "reference_image",
        },
        "consistency_contract": {
            "must_hold": [
                "scene identity",
                "background structure",
                "lighting mood",
            ],
            "allowed_variation": [
                "subject identity",
                "foreground props",
            ],
            "degradation_policy": "reference_only",
        },
        "provenance": {
            "mode": "stub_local_e2e",
            "reference_id": reference_id,
        },
    }


async def _main_async(args: argparse.Namespace) -> Dict[str, Any]:
    from app.capabilities.multi_media_studio.tools.storyboard_execution import (
        execute_storyboard,
    )
    from app.capabilities.performance_direction.tools.scene_package_generate import (
        advance_scene_package_generation_jobs,
        create_scene_package_generation_job,
        get_scene_package_generation_job,
        list_scene_package_artifacts,
        poll_scene_package_generation_job,
    )
    from app.capabilities.performance_direction.tools.session_tools import create_session
    from app.capabilities.performance_direction.tools.storyboard_gen import (
        generate_storyboard,
    )

    workspace_id = args.workspace_id
    reference_id = args.reference_id
    tenant_id = args.tenant_id
    project_id = args.project_id or f"proj_pd_scene_stub_e2e_{uuid.uuid4().hex[:12]}"
    canonical_image_ref = (
        {"file_path": args.reference_image_path}
        if str(args.reference_image_path or "").strip()
        else {"reference_id": reference_id}
    )

    _emit_step("create_session:start", workspace_id=workspace_id, reference_id=reference_id)
    create_session_result = _require_success(
        await create_session(
            workspace_id=workspace_id,
            intent={
                "emotional_function": "hold scene identity while swapping subject",
                "narrative_role": "establish_state",
                "persona_target": "character",
            },
            reference_ids=[reference_id],
            tenant_id=tenant_id,
        ),
        "create_session",
    )
    session = dict(create_session_result["session"])
    session_id = str(session["session_id"])
    _emit_step("create_session:done", session_id=session_id)

    provider_payload = {
        "operation_id": f"op_scene_stub_{uuid.uuid4().hex[:8]}",
        "submit_status": "submitted",
        "poll_status": "completed",
        "scene_package_payload": _build_stub_scene_package_payload(
            reference_id,
            canonical_image_ref=canonical_image_ref,
        ),
        "provider_response": {
            "provider": "stub",
            "note": "local deterministic E2E",
        },
    }

    _emit_step("create_job:start", session_id=session_id)
    create_job_result = _require_success(
        await create_scene_package_generation_job(
            session_id=session_id,
            provider_code="stub",
            generation_mode="generated_world",
            scene_scope="default",
            variant_id="main",
            source_reference_ids=[reference_id],
            provider_payload=provider_payload,
            tenant_id=tenant_id,
        ),
        "create_scene_package_generation_job",
    )
    job = dict(create_job_result["job"])
    job_id = str(job["job_id"])
    _emit_step("create_job:done", job_id=job_id)

    _emit_step("advance_jobs:start", session_id=session_id)
    advance_result = _require_success(
        await advance_scene_package_generation_jobs(
            session_id=session_id,
            limit=3,
            tenant_id=tenant_id,
        ),
        "advance_scene_package_generation_jobs",
    )
    _emit_step("advance_jobs:done", summary=dict(advance_result.get("summary") or {}))

    _emit_step("poll_job:start", job_id=job_id)
    poll_result = _require_success(
        await poll_scene_package_generation_job(
            job_id=job_id,
            tenant_id=tenant_id,
        ),
        "poll_scene_package_generation_job",
    )
    _emit_step("poll_job:done", status=poll_result.get("status"))

    final_job_result = _require_success(
        await get_scene_package_generation_job(
            job_id=job_id,
            tenant_id=tenant_id,
        ),
        "get_scene_package_generation_job",
    )
    final_job = dict(final_job_result["job"])

    _emit_step("list_scene_packages:start", session_id=session_id)
    scene_packages_result = _require_success(
        await list_scene_package_artifacts(
            session_id=session_id,
            scene_scope="default",
            variant_id="main",
            tenant_id=tenant_id,
        ),
        "list_scene_package_artifacts",
    )
    scene_packages: List[Dict[str, Any]] = list(scene_packages_result["scene_packages"])
    if not scene_packages:
        raise RuntimeError("scene package listing returned zero artifacts")
    selected_scene_package = dict(scene_packages[0])
    selector = dict(selected_scene_package["scene_package_selector"])
    scene_package_artifact = dict(selected_scene_package["artifact"])
    _emit_step(
        "list_scene_packages:done",
        artifact_id=scene_package_artifact.get("artifact_id"),
        selector=selector,
    )

    _emit_step("generate_storyboard:start", session_id=session_id)
    storyboard_result = _require_success(
        await generate_storyboard(
            session_id=session_id,
            workspace_id=workspace_id,
            source_type="generative",
            scene_package_selector=selector,
            render_profile={
                "profile_id": "vr_preview_local",
                "overrides": {
                    "dry_run": True,
                },
            },
            tenant_id=tenant_id,
        ),
        "generate_storyboard",
    )
    storyboard = dict(storyboard_result["storyboard"])
    storyboard_artifact = dict(storyboard_result["artifact"])
    _emit_step(
        "generate_storyboard:done",
        storyboard_id=storyboard.get("storyboard_id"),
        artifact_id=storyboard_artifact.get("artifact_id"),
    )

    _emit_step("execute_storyboard:start", project_id=project_id)
    execute_result = _require_success(
        await asyncio.wait_for(
            execute_storyboard(
                project_id=project_id,
                storyboard=storyboard,
                source_type="generative",
                tenant_id=tenant_id,
            ),
            timeout=float(args.execute_timeout_sec),
        ),
        "execute_storyboard",
    )
    _emit_step(
        "execute_storyboard:done",
        run_id=execute_result.get("run_id"),
        status=execute_result.get("status"),
    )
    run = dict(execute_result.get("run") or {})
    scene_results = list(run.get("scene_results") or [])
    first_scene_result = dict(scene_results[0]) if scene_results else {}
    clip_refs = list(first_scene_result.get("clip_refs") or [])

    summary = {
        "workspace_id": workspace_id,
        "reference_id": reference_id,
        "canonical_image_ref": canonical_image_ref,
        "project_id": project_id,
        "session_id": session_id,
        "job_id": job_id,
        "job_status": final_job.get("status"),
        "advance_summary": dict(advance_result.get("summary") or {}),
        "poll_status": poll_result.get("status"),
        "scene_package_artifact_id": scene_package_artifact.get("artifact_id"),
        "scene_package_selector": selector,
        "storyboard_artifact_id": storyboard_artifact.get("artifact_id"),
        "storyboard_id": storyboard.get("storyboard_id"),
        "run_id": execute_result.get("run_id"),
        "run_status": execute_result.get("status"),
        "scene_count": len(storyboard.get("scenes") or []),
        "clip_refs_count": len(clip_refs),
        "first_clip_ref": clip_refs[0] if clip_refs else None,
    }
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local stub-backed scene-package preview E2E."
    )
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    parser.add_argument("--reference-id", default=DEFAULT_REFERENCE_ID)
    parser.add_argument("--reference-image-path", default=DEFAULT_REFERENCE_IMAGE_PATH)
    parser.add_argument("--project-id", default="")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    parser.add_argument("--execute-timeout-sec", type=float, default=90.0)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    summary = asyncio.run(_main_async(args))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
