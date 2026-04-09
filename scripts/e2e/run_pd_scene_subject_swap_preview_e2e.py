#!/usr/bin/env python3
"""
Live-preview E2E for fixed-scene subject swap validation.

Goal:
  Prove whether the current stack can keep one scene fixed while swapping the
  foreground subject reference across multiple preview renders.

Flow:
  1. Create a PD session containing one scene reference plus N subject references.
  2. Materialize one reusable scene_package from the scene reference only.
  3. Generate one storyboard with one scene per subject reference, all replaying
     the same scene_package_selector.
  4. Execute local preview with dry_run disabled.

By default this uses the stub scene provider so the validation isolates
scene replay + subject insertion. Use --provider-code world_labs to add
live scene-generation provider behavior on top.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


BACKEND_ROOT = Path("/app/backend")
for candidate in (BACKEND_ROOT, BACKEND_ROOT / "app"):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)


DEFAULT_WORKSPACE_ID = "bac7ce63-e768-454d-96f3-3a00e8e1df69"
DEFAULT_SCENE_REFERENCE_ID = "ref_49690a59"
DEFAULT_SCENE_REFERENCE_IMAGE_PATH = (
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


def _normalize_refs(values: List[str]) -> List[str]:
    seen = set()
    normalized: List[str] = []
    for raw in values or []:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _build_stub_scene_package_payload(
    scene_reference_id: str,
    *,
    canonical_image_ref: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "package_id": f"scene.stub.{scene_reference_id}.subject-swap.v1",
        "provider": "stub",
        "generation_mode": "generated_world",
        "scene_scope": "fixed_scene",
        "variant_id": "subject_swap",
        "status": "generated",
        "source_reference_ids": [scene_reference_id],
        "control_refs": [
            {
                "control_kind": "canonical_image",
                "ref": dict(canonical_image_ref),
                "provider": "stub",
                "metadata": {"origin": "scene_reference"},
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
                "camera placement",
            ],
            "allowed_variation": [
                "subject identity",
                "subject pose",
                "foreground styling",
            ],
            "degradation_policy": "reference_only",
        },
        "provenance": {
            "mode": "subject_swap_preview_e2e",
            "scene_reference_id": scene_reference_id,
        },
    }


async def _require_live_preview_ready(comfy_address: Optional[str] = None) -> Dict[str, Any]:
    from app.capabilities.video_renderer.tools.vr_render_local_preview import (
        _resolve_preview_mode,
    )

    dry_run, resolved_address, mode = await _resolve_preview_mode(
        dry_run=None,
        comfy_address=comfy_address,
    )
    if dry_run:
        raise RuntimeError(
            "Local preview runtime is not live-ready; it would fall back to dry-run."
        )
    return {
        "mode": mode,
        "resolved_comfy_address": resolved_address,
    }


async def _require_provider_ready(provider_code: str) -> Dict[str, Any]:
    from app.capabilities.performance_direction.services.scene_generation_provider_config import (
        SceneGenerationProviderConfigService,
    )

    readiness = SceneGenerationProviderConfigService().get_provider_readiness(provider_code)
    if not readiness.get("ready"):
        raise RuntimeError(
            f"{provider_code} not ready: {json.dumps(readiness, ensure_ascii=False)}"
        )
    return readiness


async def _wait_for_scene_package(
    *,
    job_id: str,
    session_id: str,
    scene_scope: str,
    variant_id: str,
    provider_code: str,
    generation_mode: str,
    tenant_id: str,
    timeout_sec: float,
    poll_interval_sec: float,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    from app.capabilities.performance_direction.tools.scene_package_generate import (
        advance_scene_package_generation_jobs,
        get_scene_package_generation_job,
        list_scene_package_artifacts,
        poll_scene_package_generation_job,
    )

    started_at = time.monotonic()
    last_status = ""
    while True:
        if time.monotonic() - started_at > timeout_sec:
            raise TimeoutError(
                f"Timed out waiting for scene_package for job {job_id}; last status={last_status}"
            )

        advance_result = await advance_scene_package_generation_jobs(
            session_id=session_id,
            limit=3,
            tenant_id=tenant_id,
        )
        if not advance_result.get("success"):
            _emit_step("advance_jobs:error", error=advance_result.get("error"))

        poll_result = await poll_scene_package_generation_job(
            job_id=job_id,
            tenant_id=tenant_id,
        )
        if not poll_result.get("success"):
            _emit_step("poll_job:error", error=poll_result.get("error"))

        job_result = _require_success(
            await get_scene_package_generation_job(job_id=job_id, tenant_id=tenant_id),
            "get_scene_package_generation_job",
        )
        job = dict(job_result.get("job") or {})
        last_status = str(job.get("status") or "")
        _emit_step("job_status", job_id=job_id, status=last_status)

        if last_status in {"failed", "cancelled"}:
            raise RuntimeError(
                f"Scene generation job {job_id} ended in {last_status}: {job.get('last_error')}"
            )

        scene_packages_result = _require_success(
            await list_scene_package_artifacts(
                session_id=session_id,
                scene_scope=scene_scope,
                variant_id=variant_id,
                provider_code=provider_code,
                generation_mode=generation_mode,
                tenant_id=tenant_id,
            ),
            "list_scene_package_artifacts",
        )
        scene_packages = list(scene_packages_result.get("scene_packages") or [])
        if scene_packages:
            selected = dict(scene_packages[0] or {})
            selector = dict(selected.get("scene_package_selector") or {})
            artifact = dict(selected.get("artifact") or {})
            return job, artifact, selector

        await asyncio.sleep(poll_interval_sec)


async def _main_async(args: argparse.Namespace) -> Dict[str, Any]:
    from app.capabilities.multi_media_studio.tools.storyboard_execution import (
        execute_storyboard,
    )
    from app.capabilities.performance_direction.tools.scene_package_generate import (
        create_scene_package_generation_job,
    )
    from app.capabilities.performance_direction.tools.session_tools import create_session
    from app.capabilities.performance_direction.tools.storyboard_gen import (
        generate_storyboard,
    )

    workspace_id = args.workspace_id
    scene_reference_id = args.scene_reference_id
    subject_reference_ids = _normalize_refs(list(args.subject_reference_ids or []))
    if not subject_reference_ids:
        raise ValueError("--subject-reference-ids requires at least one reference id")

    tenant_id = args.tenant_id
    provider_code = str(args.provider_code or "stub").strip().lower() or "stub"
    generation_mode = str(args.generation_mode or "generated_world").strip() or "generated_world"
    scene_scope = str(args.scene_scope or "fixed_scene").strip() or "fixed_scene"
    variant_id = str(args.variant_id or "subject_swap").strip() or "subject_swap"
    project_id = args.project_id or f"proj_pd_scene_subject_swap_{uuid.uuid4().hex[:12]}"

    _emit_step("preview_readiness:start")
    preview_readiness = await _require_live_preview_ready(args.comfy_address)
    _emit_step("preview_readiness:done", **preview_readiness)

    provider_readiness = None
    if provider_code != "stub":
        _emit_step("provider_readiness:start", provider_code=provider_code)
        provider_readiness = await _require_provider_ready(provider_code)
        _emit_step("provider_readiness:done", readiness=provider_readiness)

    session_reference_ids = [scene_reference_id, *subject_reference_ids]
    _emit_step(
        "create_session:start",
        workspace_id=workspace_id,
        scene_reference_id=scene_reference_id,
        subject_reference_ids=subject_reference_ids,
    )
    create_session_result = _require_success(
        await create_session(
            workspace_id=workspace_id,
            intent={
                "emotional_function": "hold fixed scene while swapping subject identity",
                "narrative_role": "establish_state",
                "persona_target": "character",
            },
            reference_ids=session_reference_ids,
            tenant_id=tenant_id,
        ),
        "create_session",
    )
    session = dict(create_session_result["session"])
    session_id = str(session["session_id"])
    _emit_step("create_session:done", session_id=session_id)

    provider_payload = None
    if provider_code == "stub":
        canonical_image_ref = (
            {"file_path": args.scene_reference_image_path}
            if str(args.scene_reference_image_path or "").strip()
            else {"reference_id": scene_reference_id}
        )
        provider_payload = {
            "operation_id": f"op_scene_subject_swap_{uuid.uuid4().hex[:8]}",
            "submit_status": "submitted",
            "poll_status": "completed",
            "scene_package_payload": _build_stub_scene_package_payload(
                scene_reference_id,
                canonical_image_ref=canonical_image_ref,
            ),
            "provider_response": {
                "provider": "stub",
                "note": "subject swap live-preview E2E",
            },
        }

    _emit_step("create_job:start", session_id=session_id, provider_code=provider_code)
    create_job_result = _require_success(
        await create_scene_package_generation_job(
            session_id=session_id,
            provider_code=provider_code,
            generation_mode=generation_mode,
            scene_scope=scene_scope,
            variant_id=variant_id,
            source_reference_ids=[scene_reference_id],
            provider_payload=provider_payload,
            tenant_id=tenant_id,
        ),
        "create_scene_package_generation_job",
    )
    job = dict(create_job_result["job"])
    job_id = str(job["job_id"])
    _emit_step("create_job:done", job_id=job_id)

    _emit_step("wait_for_scene_package:start", job_id=job_id)
    final_job, scene_package_artifact, selector = await _wait_for_scene_package(
        job_id=job_id,
        session_id=session_id,
        scene_scope=scene_scope,
        variant_id=variant_id,
        provider_code=provider_code,
        generation_mode=generation_mode,
        tenant_id=tenant_id,
        timeout_sec=float(args.scene_job_timeout_sec),
        poll_interval_sec=float(args.scene_job_poll_interval_sec),
    )
    _emit_step(
        "wait_for_scene_package:done",
        artifact_id=scene_package_artifact.get("artifact_id"),
        selector=selector,
    )

    scene_specs = []
    for index, subject_reference_id in enumerate(subject_reference_ids, start=1):
        scene_specs.append(
            {
                "scene_id": f"swap_{index:02d}",
                "reference_ids": [subject_reference_id],
                "render_mode": "generative",
                "duration_sec": float(args.scene_duration_sec),
                "energy_level": 0.5,
            }
        )

    _emit_step("generate_storyboard:start", subject_count=len(subject_reference_ids))
    storyboard_result = _require_success(
        await generate_storyboard(
            session_id=session_id,
            workspace_id=workspace_id,
            source_type="generative",
            scene_specs=scene_specs,
            scene_package_selector=selector,
            render_profile={
                "profile_id": "vr_preview_local",
                "comfy_address": str(
                    preview_readiness.get("resolved_comfy_address")
                    or args.comfy_address
                    or ""
                ),
                "overrides": {
                    "dry_run": False,
                },
            },
            global_settings={
                "experiment": "scene_subject_swap_live_preview",
                "scene_reference_id": scene_reference_id,
                "subject_reference_ids": subject_reference_ids,
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
        scene_count=len(storyboard.get("scenes") or []),
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
    run = dict(execute_result.get("run") or {})
    scene_results = list(run.get("scene_results") or [])
    _emit_step(
        "execute_storyboard:done",
        run_id=execute_result.get("run_id"),
        status=execute_result.get("status"),
        scene_results=len(scene_results),
    )

    rendered_scene_results = []
    for index, scene_result in enumerate(scene_results):
        payload = dict(scene_result or {})
        clip_refs = list(payload.get("clip_refs") or [])
        first_clip_ref = dict(clip_refs[0] or {}) if clip_refs else {}
        storage_key = str(first_clip_ref.get("storage_key") or "")
        if "video_renderer/dry_run/" in storage_key:
            raise RuntimeError(
                f"Scene {payload.get('scene_id') or index} fell back to dry-run: {storage_key}"
            )
        rendered_scene_results.append(
            {
                "scene_id": payload.get("scene_id"),
                "subject_reference_id": subject_reference_ids[index]
                if index < len(subject_reference_ids)
                else None,
                "clip_refs_count": len(clip_refs),
                "first_clip_ref": first_clip_ref,
            }
        )

    return {
        "workspace_id": workspace_id,
        "scene_reference_id": scene_reference_id,
        "subject_reference_ids": subject_reference_ids,
        "provider_code": provider_code,
        "provider_readiness": provider_readiness,
        "preview_readiness": preview_readiness,
        "project_id": project_id,
        "session_id": session_id,
        "job_id": job_id,
        "job_status": final_job.get("status"),
        "scene_package_artifact_id": scene_package_artifact.get("artifact_id"),
        "scene_package_selector": selector,
        "storyboard_id": storyboard.get("storyboard_id"),
        "storyboard_artifact_id": storyboard_artifact.get("artifact_id"),
        "run_id": execute_result.get("run_id"),
        "run_status": execute_result.get("status"),
        "scene_results": rendered_scene_results,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run fixed-scene subject-swap live-preview E2E."
    )
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID)
    parser.add_argument("--scene-reference-id", default=DEFAULT_SCENE_REFERENCE_ID)
    parser.add_argument(
        "--scene-reference-image-path",
        default=DEFAULT_SCENE_REFERENCE_IMAGE_PATH,
        help="Used only for the stub scene provider",
    )
    parser.add_argument(
        "--subject-reference-ids",
        nargs="+",
        required=True,
        help="One or more subject reference ids to swap into the fixed scene",
    )
    parser.add_argument("--provider-code", default="stub")
    parser.add_argument("--generation-mode", default="generated_world")
    parser.add_argument("--scene-scope", default="fixed_scene")
    parser.add_argument("--variant-id", default="subject_swap")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    parser.add_argument("--comfy-address", default="")
    parser.add_argument("--scene-duration-sec", type=float, default=4.0)
    parser.add_argument("--scene-job-timeout-sec", type=float, default=600.0)
    parser.add_argument("--scene-job-poll-interval-sec", type=float, default=5.0)
    parser.add_argument("--execute-timeout-sec", type=float, default=600.0)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    summary = asyncio.run(_main_async(args))
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
