"""Top-level PD UX AOL acceptance orchestration."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from pd_ux_aol_acceptance_browser import _run_browser_acceptance
from pd_ux_aol_acceptance_common import (
    STAGES,
    _add_check,
    _first_pd_storyboard_session,
    _first_workspace_id,
    _json_get,
    _manifest,
    _manifest_has_kind,
    _project_graph,
    _repo_root,
    _safe_call,
    _stage_template,
    _storyboard_ref,
    _write_acceptance_result,
)
from pd_ux_aol_acceptance_compilers import (
    _compile_director_guidance,
    _compile_human_contribution,
    _compile_runtime_readiness,
    _compile_scene_critique,
)
from pd_ux_aol_acceptance_runtime import _run_codex_quota_preflight


def run_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    api_url = args.api_url.rstrip("/")
    control_url = args.control_url.rstrip("/")
    frontend_url = args.frontend_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stages = {stage_id: _stage_template(stage_id) for stage_id in STAGES}

    workspace_id = args.workspace_id or _first_workspace_id(api_url, args.owner_user_id)
    session_info = _first_pd_storyboard_session(api_url, workspace_id)
    session_id = args.session_id or session_info["session_id"]
    scene_id = args.scene_id or session_info["scene_id"]
    artifact_id = args.artifact_id or session_info["artifact_id"]
    project_id = (
        str((session_info.get("session") or {}).get("project_id") or "").strip()
        or None
    )
    object_ref = _storyboard_ref(
        workspace_id=workspace_id,
        session_id=session_id,
        artifact_id=artifact_id,
        scene_id=scene_id,
        frontend_url=frontend_url,
    )

    codex_quota_preflight = _safe_call(
        stages,
        "S7",
        "Codex CLI quota preflight has a runnable pool runtime before expensive E2E",
        lambda: _run_codex_quota_preflight(args, workspace_id),
        lambda payload: payload.get("status") in {"available", "skipped"},
        lambda payload: {
            "status": payload.get("status"),
            "selected_runtime_id": payload.get("selected_runtime_id"),
            "attempts": payload.get("attempts"),
        },
    )
    if (
        not args.skip_codex_quota_preflight
        and not args.continue_on_codex_quota_failure
        and (
            not isinstance(codex_quota_preflight, dict)
            or codex_quota_preflight.get("status") != "available"
        )
    ):
        _add_check(
            stages,
            "S7",
            "Codex CLI quota preflight fail-fast blocks meeting dispatch",
            False,
            evidence=codex_quota_preflight,
            failure=(
                "Codex quota preflight did not find a runnable runtime; "
                "meeting E2E was stopped before dispatch"
            ),
        )
        return _write_acceptance_result(
            started=started,
            output_dir=output_dir,
            stages=stages,
            workspace_id=workspace_id,
            session_id=session_id,
            scene_id=scene_id,
            artifact_id=artifact_id,
            project_id=project_id,
            object_ref=object_ref,
            browser_result=None,
        )

    manifest = _manifest()
    _add_check(
        stages,
        "S0",
        "PD manifest exports storyboard_scene object lane",
        _manifest_has_kind(manifest, "object_exports", "storyboard_scene"),
        evidence="object_exports.storyboard_scene",
        failure="performance_direction manifest lacks object_exports for storyboard_scene",
    )
    for lane, label in [
        ("meeting_projections", "meeting projection"),
        ("materializers", "proposal materializer"),
        ("graph_projections", "graph projection"),
    ]:
        _add_check(
            stages,
            "S0",
            f"PD manifest declares storyboard_scene {label}",
            _manifest_has_kind(manifest, lane, "storyboard_scene"),
            evidence=f"{lane}.storyboard_scene",
            failure=f"performance_direction manifest lacks {lane} for storyboard_scene",
        )
    _safe_call(
        stages,
        "S0",
        "execution backend health endpoint reports execution role",
        lambda: _json_get(f"{api_url}/healthz", timeout=10.0),
        lambda payload: payload.get("backend_role") == "execution",
        lambda payload: {"api": api_url, "health": payload},
    )
    _safe_call(
        stages,
        "S0",
        "control backend health endpoint reports control role",
        lambda: _json_get(f"{control_url}/healthz", timeout=10.0),
        lambda payload: payload.get("backend_role") == "control",
        lambda payload: {"control": control_url, "health": payload},
    )

    graph_projection = _safe_call(
        stages,
        "S0",
        "object graph API projects selected storyboard_scene",
        lambda: _project_graph(api_url, workspace_id, object_ref),
        lambda payload: bool(payload.get("projections")),
        lambda payload: {
            "projection_count": len(payload.get("projections") or []),
            "relation_count": sum(
                len(item.get("relations") or []) for item in payload.get("projections") or []
            ),
        },
    ) or {"projections": []}

    browser_result = _run_browser_acceptance(
        args=args,
        stages=stages,
        workspace_id=workspace_id,
        session_id=session_id,
        scene_id=scene_id,
        project_id=project_id,
        output_dir=output_dir,
    )

    guidance = _safe_call(
        stages,
        "S5",
        "director-guidance-compile returns guidance cards",
        lambda: _compile_director_guidance(api_url, workspace_id, scene_id, object_ref, graph_projection),
        lambda payload: payload.get("success") is True
        and bool((payload.get("guidance_state") or {}).get("guidance_cards")),
        lambda payload: {
            "compiler_version": payload.get("compiler_version"),
            "guidance_card_count": len((payload.get("guidance_state") or {}).get("guidance_cards") or []),
            "proposal_id": (payload.get("proposal_draft") or {}).get("proposal_id"),
        },
    ) or {}

    evidence_dock = guidance.get("evidence_dock_state") or {}
    attachments = list(evidence_dock.get("attachments") or [])
    decision_impacts = list(evidence_dock.get("decision_impacts") or [])
    _add_check(
        stages,
        "S4",
        "Evidence Dock exposes decision relevance and source governance before raw refs",
        bool(attachments)
        and bool(decision_impacts)
        and all(
            attachment.get("decision_relevance")
            and "source_owner" in attachment
            and "privacy_scope" in attachment
            and "provenance" in attachment
            and "removal_policy" in attachment
            and attachment.get("upgrade_options") is not None
            for attachment in attachments
        ),
        evidence={
            "attachment_count": len(attachments),
            "decision_impact_count": len(decision_impacts),
            "raw_private_memory_copied": (evidence_dock.get("metadata") or {}).get("raw_private_memory_copied"),
        },
        failure="Evidence Dock did not expose complete relevance/governance/removal-upgrade evidence",
    )
    _add_check(
        stages,
        "S5",
        "Guidance is grounded in selected object context and graph relations",
        any(
            (card.get("graph_relation_count") or 0) > 0
            for card in list((guidance.get("guidance_state") or {}).get("guidance_cards") or [])
        ),
        evidence="at least one guidance card references graph_relation_count > 0",
        failure="Director guidance cards were not grounded in object graph relations",
    )

    proposal = guidance.get("proposal_draft") or {}
    proposal_metadata = proposal.get("metadata") or {}
    _add_check(
        stages,
        "S6",
        "Guidance proposal is proposal-only and reviewable",
        proposal.get("proposal_origin") == "pd_director_guidance_compile"
        and proposal.get("materialization_tool") == "pd_reference_aware_director_compile"
        and bool(proposal.get("storyboard_scene_patch"))
        and (proposal.get("review_route") or {}).get("requires_review") is True
        and proposal_metadata.get("proposal_only") is True
        and proposal_metadata.get("side_effects") == [],
        evidence={
            "proposal_id": proposal.get("proposal_id"),
            "review_route": proposal.get("review_route"),
            "metadata": proposal_metadata,
        },
        failure="Director guidance proposal is not clearly proposal-only/reviewable",
    )

    readiness = _safe_call(
        stages,
        "S7",
        "runtime-readiness-check returns proposal-only readiness evidence",
        lambda: _compile_runtime_readiness(api_url, workspace_id, scene_id),
        lambda payload: payload.get("success") is True
        and payload.get("proposal_origin") == "pd_runtime_readiness_check"
        and bool(payload.get("readiness_check"))
        and (payload.get("metadata") or {}).get("side_effects") == [],
        lambda payload: {
            "proposal_id": payload.get("proposal_id"),
            "recommended_route": (payload.get("readiness_check") or {}).get("recommended_route"),
            "risk_level": (payload.get("readiness_check") or {}).get("risk_level"),
        },
    ) or {}

    critique = _safe_call(
        stages,
        "S7",
        "scene-critique joins readiness, preview refs, and decision proposals",
        lambda: _compile_scene_critique(
            api_url,
            workspace_id,
            scene_id,
            object_ref,
            readiness.get("readiness_check") or {},
        ),
        lambda payload: payload.get("success") is True
        and payload.get("proposal_origin") == "pd_scene_critique"
        and bool(payload.get("decision_items"))
        and bool(payload.get("review_candidates"))
        and (payload.get("metadata") or {}).get("side_effects") == [],
        lambda payload: {
            "proposal_id": payload.get("proposal_id"),
            "decision_items": len(payload.get("decision_items") or []),
            "review_candidates": len(payload.get("review_candidates") or []),
        },
    ) or {}
    _add_check(
        stages,
        "S7",
        "Readiness and critique produce graph/inspector-safe scene patch evidence",
        bool((readiness.get("storyboard_scene_patch") or {}).get("scene_manifest"))
        and bool((critique.get("storyboard_scene_patch") or {}).get("scene_manifest")),
        evidence={
            "readiness_scene_manifest_keys": sorted(
                ((readiness.get("storyboard_scene_patch") or {}).get("scene_manifest") or {}).keys()
            ),
            "critique_scene_manifest_keys": sorted(
                ((critique.get("storyboard_scene_patch") or {}).get("scene_manifest") or {}).keys()
            ),
        },
        failure="Runtime readiness/critique did not emit scene_manifest evidence for graph/inspector display",
    )

    human = _safe_call(
        stages,
        "S8",
        "human-contribution-compile returns governed human evidence",
        lambda: _compile_human_contribution(api_url, workspace_id, scene_id),
        lambda payload: payload.get("success") is True
        and payload.get("proposal_origin") == "pd_human_contribution_compile"
        and bool(((payload.get("human_contribution_ledger") or {}).get("records") or []))
        and not ((payload.get("human_contribution_evidence_state") or {}).get("missing_governance_fields") or [])
        and (payload.get("metadata") or {}).get("raw_media_copied") is False,
        lambda payload: {
            "proposal_id": payload.get("proposal_id"),
            "record_count": len((payload.get("human_contribution_ledger") or {}).get("records") or []),
            "missing_governance_fields": (
                payload.get("human_contribution_evidence_state") or {}
            ).get("missing_governance_fields"),
        },
    ) or {}
    human_state = human.get("human_contribution_evidence_state") or {}
    human_profiles = human_state.get("workstation_cost_profiles") or []
    _add_check(
        stages,
        "S8",
        "Human contribution evidence includes consent, usage, provenance, and workstation cost",
        bool(human_profiles)
        and all(
            record.get("consent_scope")
            and record.get("usage_scope")
            and record.get("provenance")
            and record.get("workstation_cost_profile")
            for record in list((human.get("human_contribution_ledger") or {}).get("records") or [])
        ),
        evidence={
            "workstation_cost_profiles": human_profiles,
            "evidence_by_decision": human_state.get("evidence_by_decision"),
        },
        failure="Human contribution record is missing governance or workstation-cost evidence",
    )

    control_health = _safe_call(
        stages,
        "S9",
        "backend-control 8220 exposes control role",
        lambda: _json_get(f"{control_url}/healthz", timeout=10.0),
        lambda payload: payload.get("backend_role") == "control",
        lambda payload: {"control": control_url, "health": payload},
    ) or {}
    execution_health = _safe_call(
        stages,
        "S9",
        "execution 8200 exposes execution role",
        lambda: _json_get(f"{api_url}/healthz", timeout=10.0),
        lambda payload: payload.get("backend_role") == "execution",
        lambda payload: {"api": api_url, "health": payload},
    ) or {}
    installed = _safe_call(
        stages,
        "S9",
        "installed capabilities endpoint responds through frontend/control proxy",
        lambda: _json_get(
            f"{frontend_url}/api/v1/capability-packs/installed-capabilities",
            timeout=60.0,
        ),
        lambda payload: isinstance(payload, list),
        lambda payload: {"installed_count": len(payload) if isinstance(payload, list) else None},
    ) or []
    installed_codes = [item.get("code") or item.get("id") for item in list(installed or [])]
    _add_check(
        stages,
        "S9",
        "installed capabilities list exposes performance_direction through frontend/control proxy",
        "performance_direction" in installed_codes,
        evidence={"installed_count": len(installed_codes), "has_performance_direction": "performance_direction" in installed_codes},
        failure="Installed capability list does not include performance_direction",
    )
    tool_list = _safe_call(
        stages,
        "S9",
        "execution tool registry endpoint responds",
        lambda: _json_get(f"{api_url}/api/v1/tools/?enabled_only=true", timeout=90.0),
        lambda payload: isinstance(payload, list),
        lambda payload: {"tool_count": len(payload) if isinstance(payload, list) else None},
    ) or []
    tool_ids = [item.get("tool_id") or item.get("name") for item in list(tool_list or [])]
    _add_check(
        stages,
        "S9",
        "PD director guidance tool is discoverable after pack install",
        any(str(tool_id).endswith("pd_director_guidance_compile") for tool_id in tool_ids),
        evidence={"matching_tools": [tool_id for tool_id in tool_ids if "pd_director_guidance_compile" in str(tool_id)]},
        failure="Tool registry did not expose pd_director_guidance_compile",
    )
    legacy_schema_path = _repo_root() / "data" / "runtime_contracts" / "shared" / "schemas"
    _add_check(
        stages,
        "S9",
        "PD pack runs from installed pack path without legacy shared.schemas mirror",
        (_repo_root() / "backend" / "app" / "capabilities" / "performance_direction").exists()
        and not legacy_schema_path.exists(),
        evidence={
            "installed_pack_path": str(
                _repo_root() / "backend" / "app" / "capabilities" / "performance_direction"
            ),
            "legacy_shared_schema_path_exists": legacy_schema_path.exists(),
        },
        failure="Legacy shared.schemas mirror path still exists or installed pack path is missing",
    )

    return _write_acceptance_result(
        started=started,
        output_dir=output_dir,
        stages=stages,
        workspace_id=workspace_id,
        session_id=session_id,
        scene_id=scene_id,
        artifact_id=artifact_id,
        project_id=project_id,
        object_ref=object_ref,
        browser_result=browser_result,
    )
