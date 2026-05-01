#!/usr/bin/env python3
"""S0-S9 acceptance runner for the PD UX AOL meeting graph plan.

This is intentionally broader than the old browser smoke. It validates the
live installed path against the explicit true/false checklist in plan 06:

PD pack manifest -> local-core AOL object selection -> role-bearing meeting
attach -> object graph shell -> Evidence Dock / Director Guidance -> runtime
readiness + critique -> human contribution evidence -> control-plane install
proof.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import yaml
from playwright.sync_api import sync_playwright


DEFAULT_FRONTEND_URL = "http://127.0.0.1:8300"
DEFAULT_API_URL = "http://127.0.0.1:8200"
DEFAULT_CONTROL_URL = "http://127.0.0.1:8220"
DEFAULT_OWNER_USER_ID = "default-user"

STAGES: dict[str, str] = {
    "S0": "Foundation exists",
    "S1": "Object selection feels explicit",
    "S2": "Role-aware context is visible",
    "S3": "Graph Shell shows object neighborhood",
    "S4": "Evidence Dock explains decision relevance",
    "S5": "Director Guidance turns context into choices",
    "S6": "Proposal stays reviewable",
    "S7": "Runtime readiness and critique join the same surface",
    "S8": "Human contribution evidence joins as object evidence",
    "S9": "Installed proof uses correct control plane",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _json_request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 30.0,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc
    return json.loads(text) if text else {}


def _json_get(url: str, *, timeout: float = 30.0) -> Any:
    return _json_request("GET", url, timeout=timeout)


def _json_post(url: str, payload: dict[str, Any], *, timeout: float = 30.0) -> Any:
    return _json_request("POST", url, payload, timeout=timeout)


def _first_workspace_id(api_url: str, owner_user_id: str) -> str:
    query = urllib.parse.urlencode({"owner_user_id": owner_user_id})
    payload = _json_get(f"{api_url}/api/v1/workspaces?{query}", timeout=45.0)
    workspaces = payload if isinstance(payload, list) else payload.get("workspaces", [])
    for workspace in workspaces:
        workspace_id = str(workspace.get("id") or "").strip()
        if workspace_id:
            return workspace_id
    raise RuntimeError(f"No workspace found for owner_user_id={owner_user_id!r}")


def _first_pd_storyboard_session(api_url: str, workspace_id: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"workspace_id": workspace_id, "limit": 10})
    payload = _json_get(
        f"{api_url}/api/v1/capabilities/performance_direction/sessions?{query}",
        timeout=45.0,
    )
    sessions = payload.get("sessions", []) if isinstance(payload, dict) else []
    for session in sessions:
        session_id = str(session.get("session_id") or "").strip()
        summary = session.get("storyboard_summary") or {}
        scene_ids = summary.get("scene_ids") or []
        artifact_id = str(
            session.get("latest_storyboard_artifact_id") or summary.get("artifact_id") or ""
        ).strip()
        if session_id and scene_ids and artifact_id:
            return {
                "session_id": session_id,
                "scene_id": str(scene_ids[0]),
                "artifact_id": artifact_id,
                "session": session,
            }
    raise RuntimeError(f"No PD storyboard session found for workspace_id={workspace_id!r}")


def _storyboard_ref(
    *,
    workspace_id: str,
    session_id: str,
    artifact_id: str,
    scene_id: str,
    frontend_url: str,
) -> dict[str, Any]:
    object_id = f"{session_id}:{artifact_id}:{scene_id}"
    source_surface = (
        f"{frontend_url}/workspaces/{workspace_id}"
        f"/capabilities/performance_direction/sessions/{session_id}"
    )
    return {
        "uri": f"mindscape://performance_direction/storyboard_scene/{object_id}",
        "owner_pack": "performance_direction",
        "object_kind": "storyboard_scene",
        "object_id": object_id,
        "workspace_id": workspace_id,
        "selector": {
            "selector_type": "storyboard_scene",
            "scene_id": scene_id,
            "metadata": {
                "session_id": session_id,
                "artifact_id": artifact_id,
            },
        },
        "source_surface": source_surface,
    }


def _stage_template(stage_id: str) -> dict[str, Any]:
    return {
        "label": STAGES[stage_id],
        "required_for_done": True,
        "passed": False,
        "checks": [],
        "evidence": [],
        "failures": [],
    }


def _add_check(
    stages: dict[str, dict[str, Any]],
    stage_id: str,
    name: str,
    passed: bool,
    *,
    evidence: Any = None,
    failure: str | None = None,
) -> None:
    check = {"name": name, "passed": bool(passed)}
    if evidence is not None:
        check["evidence"] = evidence
    if not passed and failure:
        check["failure"] = failure
        stages[stage_id]["failures"].append(failure)
    stages[stage_id]["checks"].append(check)


def _add_evidence(
    stages: dict[str, dict[str, Any]],
    stage_id: str,
    name: str,
    value: Any,
) -> None:
    stages[stage_id]["evidence"].append({"name": name, "value": value})


def _finalize_stages(stages: dict[str, dict[str, Any]]) -> None:
    for stage in stages.values():
        checks = stage["checks"]
        stage["passed"] = bool(checks) and all(check["passed"] for check in checks) and not stage["failures"]


def _safe_call(
    stages: dict[str, dict[str, Any]],
    stage_id: str,
    name: str,
    fn: Callable[[], Any],
    predicate: Callable[[Any], bool],
    evidence_fn: Callable[[Any], Any] | None = None,
) -> Any:
    try:
        value = fn()
    except Exception as exc:  # noqa: BLE001 - acceptance output must record exact failure.
        _add_check(stages, stage_id, name, False, failure=str(exc))
        return None
    passed = predicate(value)
    _add_check(
        stages,
        stage_id,
        name,
        passed,
        evidence=evidence_fn(value) if evidence_fn else value,
        failure=None if passed else f"{name} returned unexpected value",
    )
    return value


def _manifest() -> dict[str, Any]:
    manifest_path = _repo_root() / "backend" / "app" / "capabilities" / "performance_direction" / "manifest.yaml"
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8"))


def _manifest_has_kind(manifest: dict[str, Any], lane: str, kind: str) -> bool:
    return any(item.get("kind") == kind for item in list(manifest.get(lane) or []))


def _request_failure_text(request: Any) -> str:
    failure = request.failure
    if callable(failure):
        failure = failure()
    return str(failure or "")


def _ignored_failed_request(request: Any) -> bool:
    failure = _request_failure_text(request)
    return failure == "net::ERR_ABORTED" and "/api/v1/cloud-sync/status" in request.url


def _project_graph(api_url: str, workspace_id: str, object_ref: dict[str, Any]) -> dict[str, Any]:
    return _json_post(
        f"{api_url}/api/v1/workspaces/{workspace_id}/object-graph/project",
        {"objects": [object_ref], "include_relations": True, "include_summaries": True},
        timeout=45.0,
    )


def _workspace_runtime_state(api_url: str, workspace_id: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"workspace_id": workspace_id})
    return {
        "agents": _json_get(f"{api_url}/api/v1/workspaces/{workspace_id}/agents", timeout=30.0),
        "route_policy": _json_get(
            f"{api_url}/api/v1/settings/model-route-registry/workspace-executor?{query}",
            timeout=30.0,
        ),
    }


def _bound_runtime_ids(route_policy: dict[str, Any]) -> list[str]:
    runtime_ids: list[str] = []
    for key in ["primary_executor_runtime", "resolved_executor_runtime"]:
        value = str(route_policy.get(key) or "").strip()
        if value and value not in runtime_ids:
            runtime_ids.append(value)
    for surface, state in (route_policy.get("surfaces") or {}).items():
        if not isinstance(state, dict):
            continue
        if state.get("enabled") and surface not in runtime_ids:
            runtime_ids.append(str(surface))
        preferred = str(state.get("preferred_runtime_id") or "").strip()
        if preferred and preferred not in runtime_ids:
            runtime_ids.append(preferred)
    for runtime_id in list(route_policy.get("dispatch_chain") or []):
        runtime_id = str(runtime_id or "").strip()
        if runtime_id and runtime_id not in runtime_ids:
            runtime_ids.append(runtime_id)
    return runtime_ids


def _workspace_agent_statuses(runtime_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    agents_payload = runtime_state.get("agents") or {}
    agents = agents_payload.get("agents") if isinstance(agents_payload, dict) else []
    return {
        str(agent.get("id")): {
            "status": agent.get("status"),
            "transport": agent.get("transport"),
            "reason": agent.get("reason"),
        }
        for agent in list(agents or [])
        if isinstance(agent, dict) and agent.get("id")
    }


def _runtime_route_evidence(runtime_state: dict[str, Any]) -> dict[str, Any]:
    route_policy = runtime_state.get("route_policy") or {}
    bound_runtime_ids = _bound_runtime_ids(route_policy)
    agent_statuses = _workspace_agent_statuses(runtime_state)
    available_bound_runtime_ids = [
        runtime_id
        for runtime_id in bound_runtime_ids
        if (agent_statuses.get(runtime_id) or {}).get("status") == "available"
    ]
    return {
        "bound_runtime_ids": bound_runtime_ids,
        "available_bound_runtime_ids": available_bound_runtime_ids,
        "agent_statuses": agent_statuses,
        "route_policy": {
            "primary_executor_runtime": route_policy.get("primary_executor_runtime"),
            "resolved_executor_runtime": route_policy.get("resolved_executor_runtime"),
            "dispatch_chain": route_policy.get("dispatch_chain"),
            "fallback_policy": route_policy.get("fallback_policy"),
            "surfaces": route_policy.get("surfaces"),
        },
    }


def _wait_workspace_runtime_available(
    api_url: str,
    workspace_id: str,
    *,
    timeout_seconds: float = 180.0,
    poll_seconds: float = 2.0,
) -> dict[str, Any]:
    started = time.time()
    deadline = started + timeout_seconds
    last_evidence: dict[str, Any] | None = None
    last_error: str | None = None
    poll_count = 0
    while time.time() < deadline:
        poll_count += 1
        try:
            state = _workspace_runtime_state(api_url, workspace_id)
            evidence = _runtime_route_evidence(state)
            last_evidence = evidence
            if evidence.get("available_bound_runtime_ids"):
                evidence["poll_status"] = "ready"
                evidence["poll_count"] = poll_count
                evidence["wait_ms"] = round((time.time() - started) * 1000)
                return evidence
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(poll_seconds)
    evidence = dict(last_evidence or {})
    evidence["poll_status"] = "timeout"
    evidence["poll_count"] = poll_count
    evidence["wait_ms"] = round((time.time() - started) * 1000)
    if last_error:
        evidence["last_error"] = last_error
    return evidence


def _meeting_runtime_evidence(api_url: str, workspace_id: str, meeting_id: str) -> dict[str, Any]:
    events_payload = _json_get(
        f"{api_url}/api/v1/workspaces/{workspace_id}/meeting-sessions/{meeting_id}/events?limit=120",
        timeout=10.0,
    )
    thread_events_payload = _json_get(
        f"{api_url}/api/v1/workspaces/{workspace_id}/events?thread_id={meeting_id}&limit=120",
        timeout=10.0,
    )
    graph_payload = _json_get(
        f"{api_url}/api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/execution-graph?limit=200",
        timeout=10.0,
    )
    session_payload = _json_get(
        f"{api_url}/api/v1/workspaces/{workspace_id}/meeting-sessions/{meeting_id}",
        timeout=10.0,
    )
    graph_nodes = list(graph_payload.get("nodes") or [])
    failed_graph_nodes = [
        node
        for node in graph_nodes
        if str((node or {}).get("status") or "").lower() in {"failed", "error", "blocked"}
    ]
    metadata = session_payload.get("metadata") or {}
    action_items = list(session_payload.get("action_items") or [])
    return {
        "meeting_event_count": len(events_payload.get("events") or []),
        "thread_event_count": len(thread_events_payload.get("events") or []),
        "execution_graph_node_count": len(graph_nodes),
        "execution_graph_edge_count": len(graph_payload.get("edges") or []),
        "failed_execution_graph_node_count": len(failed_graph_nodes),
        "failed_execution_graph_nodes": [
            {
                "id": node.get("id"),
                "title": node.get("title"),
                "status": node.get("status"),
                "detail": node.get("detail"),
            }
            for node in failed_graph_nodes[:8]
            if isinstance(node, dict)
        ],
        "session_trace_count": len(session_payload.get("traces") or []),
        "session_id": session_payload.get("id"),
        "session_thread_id": session_payload.get("thread_id"),
        "session_status": session_payload.get("status"),
        "minutes_length": len(str(session_payload.get("minutes_md") or "")),
        "action_item_count": len(action_items),
        "completion_status": metadata.get("completion_status"),
        "execution_ids": metadata.get("execution_ids") or [],
        "executor_runtime_id": (
            (metadata.get("execution_context_snapshot") or {}).get("executor_runtime_id")
        ),
        "round_count": session_payload.get("round_count"),
    }


def _dispatch_meeting_runtime_command(
    api_url: str,
    workspace_id: str,
    meeting_id: str,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message": (
            "06 acceptance S7 runtime command. Use the attached target "
            "storyboard_scene only. Produce one concise director decision with "
            "schedule_id, entity_refs, anchor_ids, and one verification action item. "
            "Do not dispatch a playbook unless all required playbook inputs are present."
        ),
        "mode": "meeting",
        "stream": True,
        "thread_id": meeting_id,
        "action_params": {
            "meeting_command": True,
            "meeting_id": meeting_id,
            "meeting_session_id": meeting_id,
            "thread_id": meeting_id,
        },
    }
    if project_id:
        payload["project_id"] = project_id
    response = _json_post(
        f"{api_url}/api/v1/workspaces/{workspace_id}/chat",
        payload,
        timeout=30.0,
    )
    return {"request": payload, "response": response}


def _runtime_evidence_ready(payload: dict[str, Any]) -> bool:
    return (
        int(payload.get("round_count") or 0) > 0
        and int(payload.get("minutes_length") or 0) > 0
    )


def _wait_meeting_runtime_evidence(
    api_url: str,
    workspace_id: str,
    meeting_id: str,
    *,
    timeout_seconds: float = 180.0,
    poll_seconds: float = 2.0,
) -> dict[str, Any]:
    started = time.time()
    deadline = started + timeout_seconds
    last_payload: dict[str, Any] | None = None
    last_error: str | None = None
    poll_count = 0
    while time.time() < deadline:
        poll_count += 1
        try:
            payload = _meeting_runtime_evidence(api_url, workspace_id, meeting_id)
            last_payload = payload
            if _runtime_evidence_ready(payload):
                payload["poll_status"] = "ready"
                payload["poll_count"] = poll_count
                payload["wait_ms"] = round((time.time() - started) * 1000)
                return payload
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(poll_seconds)
    payload = dict(last_payload or {})
    payload["poll_status"] = "timeout"
    payload["poll_count"] = poll_count
    payload["wait_ms"] = round((time.time() - started) * 1000)
    if last_error:
        payload["last_error"] = last_error
    return payload


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


def _run_browser_acceptance(
    *,
    args: argparse.Namespace,
    stages: dict[str, dict[str, Any]],
    workspace_id: str,
    session_id: str,
    scene_id: str,
    project_id: str | None,
    output_dir: Path,
) -> dict[str, Any]:
    frontend_url = args.frontend_url.rstrip("/")
    session_url = (
        f"{frontend_url}/workspaces/{workspace_id}"
        f"/capabilities/performance_direction/sessions/{session_id}"
    )
    scene_selector = f'[data-testid="pd-aol-scene-{scene_id}"]'
    console_errors: list[str] = []
    failed_requests: list[str] = []
    captured_requests: list[dict[str, Any]] = []
    captured_attach: dict[str, Any] | None = None
    captured_graph: dict[str, Any] | None = None

    def should_capture_network(url: str) -> bool:
        return any(
            marker in url
            for marker in [
                "/object-graph/project",
                "/objects/sync",
                "/execution-graph",
                "/meeting-sessions/",
                "/events?",
            ]
        )

    def record_failed_request(request: Any) -> None:
        if _ignored_failed_request(request):
            return
        failed_requests.append(
            f"{request.method} {request.url} :: {_request_failure_text(request)}"
        )

    def capture_request(request: Any) -> None:
        if not should_capture_network(request.url):
            return
        captured_requests.append(
            {
                "method": request.method,
                "url": request.url,
                "post_data": request.post_data[:4000] if request.post_data else None,
            }
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={"width": 1440, "height": 1600})
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text)
            if msg.type in {"error"} and "baseline-browser-mapping" not in msg.text
            else None,
        )
        page.on("request", capture_request)
        page.on("requestfailed", record_failed_request)

        def capture_response(response: Any) -> None:
            nonlocal captured_attach, captured_graph
            if response.status >= 400:
                body = ""
                try:
                    body = response.text()[:1200]
                except Exception as exc:  # noqa: BLE001
                    body = f"<could not read response body: {exc}>"
                failed_requests.append(
                    f"{response.request.method} {response.url} :: HTTP {response.status}: {body}"
                )
                return
            if "/object-meeting-attach" in response.url:
                try:
                    captured_attach = response.json()
                except Exception as exc:  # noqa: BLE001
                    failed_requests.append(f"could not parse attach response: {exc}")
            if "/object-graph/project" in response.url:
                try:
                    captured_graph = response.json()
                except Exception as exc:  # noqa: BLE001
                    failed_requests.append(f"could not parse graph response: {exc}")

        page.on("response", capture_response)

        page.goto(session_url, wait_until="commit", timeout=args.timeout_ms)
        page.wait_for_selector('[data-testid="aol-global-anchor"]', timeout=args.timeout_ms)
        page.wait_for_selector(scene_selector, timeout=args.timeout_ms)

        page.locator('[data-testid="aol-global-anchor"]').click(timeout=5_000)
        page.get_by_text("Select an object on this page").wait_for(timeout=10_000)
        page.locator(scene_selector).click(timeout=10_000, force=True)

        page.wait_for_selector('[data-testid="aol-host-panel"]', timeout=args.timeout_ms)
        page.wait_for_selector('[data-testid="aol-role-control"]', timeout=args.timeout_ms)
        page.wait_for_selector('[data-testid="aol-role-option-target"]', timeout=args.timeout_ms)

        panel_text = page.locator('[data-testid="aol-host-panel"]').inner_text(timeout=10_000)
        _add_check(
            stages,
            "S1",
            "AOL host panel exposes owner/kind/id/source without raw JSON default",
            all(token in panel_text for token in ["performance_direction", "storyboard_scene", scene_id])
            and "{" not in panel_text[:600],
            evidence=panel_text[:900],
            failure="AOL host panel did not show explicit owner/kind/object identity in bounded UI text",
        )
        _add_check(
            stages,
            "S2",
            "Role control exposes target/source/baseline/constraint/evidence options",
            all(
                page.locator(f'[data-testid="aol-role-option-{role}"]').count() > 0
                for role in ["target", "source", "baseline", "constraint", "evidence"]
            ),
            evidence="role options target/source/baseline/constraint/evidence",
            failure="AOL role picker is missing one or more required object roles",
        )

        page.locator('[data-testid="aol-role-option-target"]').click(timeout=5_000)
        panel_text_after_role = page.locator('[data-testid="aol-host-panel"]').inner_text(timeout=10_000)
        _add_check(
            stages,
            "S2",
            "Selected target role is visible before meeting attach",
            "Target" in panel_text_after_role,
            evidence=panel_text_after_role[:900],
            failure="Target role was not visible in the AOL host panel",
        )

        page.get_by_role("button", name="Open Meeting").click(timeout=10_000)
        page.wait_for_selector('[data-testid="aol-meeting-pane"]', timeout=args.timeout_ms)
        page.wait_for_selector('[data-testid="aol-meeting-bottom-shell"]', timeout=args.timeout_ms)
        page.wait_for_selector('[data-testid="meeting-header-toolbar"]', timeout=args.timeout_ms)

        page.locator('[data-testid="meeting-object-context-toggle"]').click(timeout=5_000)
        page.wait_for_selector('[data-testid="meeting-object-context-panel"]', timeout=args.timeout_ms)
        object_context_text = page.locator('[data-testid="meeting-object-context-panel"]').inner_text(timeout=10_000)
        _add_check(
            stages,
            "S1",
            "Meeting object context remains readable after attach",
            all(
                token in object_context_text
                for token in ["OBJECT CONTEXT", "OWNER", "performance_direction", "KIND", "storyboard scene", "SOURCE"]
            )
            and "{" not in object_context_text[:600],
            evidence=object_context_text[:900],
            failure="Meeting object context panel did not retain bounded owner/kind/source identity",
        )

        graph_wait_deadline = time.time() + max(15, args.timeout_ms / 1000)
        while captured_graph is None and time.time() < graph_wait_deadline:
            page.wait_for_timeout(250)

        page.locator('[data-testid="meeting-inspector-tab-graph"]').click(timeout=5_000)
        page.wait_for_selector('[data-testid="meeting-object-graph-panel"]', timeout=args.timeout_ms)
        render_wait_deadline = time.time() + max(15, args.timeout_ms / 1000)
        graph_panel_text = page.locator('[data-testid="meeting-object-graph-panel"]').inner_text(timeout=10_000)
        while "Loading bounded relation projections" in graph_panel_text and time.time() < render_wait_deadline:
            page.wait_for_timeout(250)
            graph_panel_text = page.locator('[data-testid="meeting-object-graph-panel"]').inner_text(timeout=10_000)
        graph_relation_count = 0
        if captured_graph:
            graph_relation_count = sum(
                len(projection.get("relations") or [])
                for projection in list(captured_graph.get("projections") or [])
            )
        _add_check(
            stages,
            "S3",
            "Meeting shell renders object graph panel separate from trace",
            "Bounded object graph" in graph_panel_text
            and page.locator('[data-testid="meeting-trace-panel"]').count() == 0,
            evidence=graph_panel_text[:900],
            failure="Graph inspector panel did not render as a separate bounded object graph surface",
        )
        _add_check(
            stages,
            "S3",
            "Object graph response includes owner-pack relations",
            bool(captured_graph and graph_relation_count > 0),
            evidence={
                "projection_count": len(captured_graph.get("projections") or []) if captured_graph else 0,
                "relation_count": graph_relation_count,
            },
            failure="Browser flow did not receive graph relations from /object-graph/project",
        )

        page.locator('[data-testid="meeting-inspector-tab-trace"]').click(timeout=5_000)
        page.wait_for_selector('[data-testid="meeting-trace-panel"]', timeout=args.timeout_ms)
        _add_check(
            stages,
            "S3",
            "Trace inspector remains separate from graph inspector",
            page.locator('[data-testid="meeting-trace-panel"]').count() == 1
            and page.locator('[data-testid="meeting-object-graph-panel"]').count() == 0,
            evidence="meeting-trace-panel visible after switching from graph",
            failure="Trace and graph evidence are not separated in the inspector shell",
        )

        screenshot_path = output_dir / "pd-ux-aol-acceptance.png"
        screenshot_path.write_bytes(page.screenshot(full_page=True))
        browser.close()

    if captured_attach:
        _add_check(
            stages,
            "S2",
            "Attach API returns role-bearing meeting attachment",
            any(item.get("role") == "target" for item in list(captured_attach.get("attachments") or []))
            and bool(captured_attach.get("meeting_id")),
            evidence={
                "meeting_id": captured_attach.get("meeting_id"),
                "status": captured_attach.get("status"),
                "roles": [item.get("role") for item in list(captured_attach.get("attachments") or [])],
            },
            failure="Attach response did not include target role metadata",
        )
        meeting_id = str(captured_attach.get("meeting_id") or "")
        if meeting_id:
            meeting_payload = _json_get(
                f"{args.api_url.rstrip('/')}/api/v1/workspaces/{workspace_id}/meeting-sessions/{meeting_id}",
                timeout=30.0,
            )
            metadata = meeting_payload.get("metadata") or {}
            _add_check(
                stages,
                "S2",
                "Meeting session persists addressable_object_layer metadata",
                bool(metadata.get("addressable_object_layer")),
                evidence=metadata.get("addressable_object_layer"),
                failure="Meeting session did not persist addressable_object_layer metadata",
            )

            runtime_state = _safe_call(
                stages,
                "S7",
                "Workspace-specific runtime state is queryable for the active meeting workspace",
                lambda: _workspace_runtime_state(args.api_url.rstrip("/"), workspace_id),
                lambda payload: isinstance((payload.get("agents") or {}).get("agents"), list)
                and isinstance(payload.get("route_policy"), dict),
                lambda payload: {
                    "agents": _workspace_agent_statuses(payload),
                    "route_policy": {
                        "primary_executor_runtime": (payload.get("route_policy") or {}).get(
                            "primary_executor_runtime"
                        ),
                        "resolved_executor_runtime": (payload.get("route_policy") or {}).get(
                            "resolved_executor_runtime"
                        ),
                        "dispatch_chain": (payload.get("route_policy") or {}).get("dispatch_chain"),
                        "fallback_policy": (payload.get("route_policy") or {}).get("fallback_policy"),
                        "surfaces": (payload.get("route_policy") or {}).get("surfaces"),
                    },
                },
            )
            if isinstance(runtime_state, dict):
                route_evidence = _runtime_route_evidence(runtime_state)
                bound_runtime_ids = route_evidence["bound_runtime_ids"]
                _add_check(
                    stages,
                    "S7",
                    "Meeting command dispatch has a configured workspace runtime route",
                    bool(bound_runtime_ids),
                    evidence={
                        "bound_runtime_ids": bound_runtime_ids,
                        "route_policy": route_evidence["route_policy"],
                    },
                    failure="Workspace executor route has no primary/resolved runtime, enabled surface, preferred runtime, or dispatch chain",
                )
                _safe_call(
                    stages,
                    "S7",
                    "Configured workspace runtime is online for this workspace",
                    lambda: _wait_workspace_runtime_available(
                        args.api_url.rstrip("/"),
                        workspace_id,
                    ),
                    lambda payload: bool(payload.get("available_bound_runtime_ids")),
                    lambda payload: payload,
                )

            command_dispatch = _safe_call(
                stages,
                "S7",
                "Meeting command is posted to the attached meeting session",
                lambda: _dispatch_meeting_runtime_command(
                    args.api_url.rstrip("/"),
                    workspace_id,
                    meeting_id,
                    project_id=project_id,
                ),
                lambda payload: (payload.get("response") or {}).get("status") == "accepted"
                and bool((payload.get("response") or {}).get("event_id")),
                lambda payload: {
                    "meeting_id": meeting_id,
                    "thread_id": (payload.get("request") or {}).get("thread_id"),
                    "meeting_session_id": (
                        (payload.get("request") or {}).get("action_params") or {}
                    ).get("meeting_session_id"),
                    "response": payload.get("response"),
                },
            )
            if isinstance(command_dispatch, dict):
                runtime_evidence = _safe_call(
                    stages,
                    "S7",
                    "Meeting command produces persisted runtime output on the attached session",
                    lambda: _wait_meeting_runtime_evidence(
                        args.api_url.rstrip("/"),
                        workspace_id,
                        meeting_id,
                    ),
                    lambda payload: isinstance(payload, dict)
                    and payload.get("poll_status") == "ready"
                    and payload.get("session_id") == meeting_id
                    and payload.get("session_thread_id") == meeting_id
                    and payload.get("session_status") not in {"failed", "aborted"}
                    and int(payload.get("round_count") or 0) > 0
                    and int(payload.get("minutes_length") or 0) > 0,
                    lambda payload: payload,
                )
            else:
                runtime_evidence = _safe_call(
                    stages,
                    "S7",
                    "Active meeting runtime event surfaces are readable",
                    lambda: _meeting_runtime_evidence(args.api_url.rstrip("/"), workspace_id, meeting_id),
                    lambda payload: isinstance(payload, dict),
                    lambda payload: payload,
                )
            if isinstance(runtime_evidence, dict):
                _add_check(
                    stages,
                    "S7",
                    "Active meeting has no failed downstream execution nodes",
                    int(runtime_evidence.get("failed_execution_graph_node_count") or 0) == 0,
                    evidence=runtime_evidence,
                    failure="Meeting runtime produced failed/error/blocked execution graph nodes",
                )
    else:
        _add_check(
            stages,
            "S2",
            "Attach API returns role-bearing meeting attachment",
            False,
            failure="Browser flow did not capture /object-meeting-attach response",
        )

    return {
        "session_url": session_url,
        "screenshot": str(screenshot_path),
        "console_errors": console_errors,
        "failed_requests": failed_requests,
        "captured_requests": captured_requests,
        "captured_attach_meeting_id": (
            captured_attach.get("meeting_id") if isinstance(captured_attach, dict) else None
        ),
        "captured_graph_projection_count": (
            len(captured_graph.get("projections") or []) if isinstance(captured_graph, dict) else 0
        ),
    }


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
            "relation_count": sum(len(item.get("relations") or []) for item in payload.get("projections") or []),
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

    _add_evidence(stages, "S0", "workspace_id", workspace_id)
    _add_evidence(stages, "S0", "session_id", session_id)
    _add_evidence(stages, "S0", "scene_id", scene_id)
    _add_evidence(stages, "S0", "artifact_id", artifact_id)
    _finalize_stages(stages)
    failed = [stage_id for stage_id, stage in stages.items() if not stage["passed"]]

    result = {
        "status": "passed" if not failed else "failed",
        "duration_ms": round((time.time() - started) * 1000),
        "failed_stages": failed,
        "context": {
            "workspace_id": workspace_id,
            "session_id": session_id,
            "scene_id": scene_id,
            "artifact_id": artifact_id,
            "project_id": project_id,
            "object_ref": object_ref,
        },
        "stages": stages,
        "browser": browser_result,
    }
    result_path = output_dir / "pd-ux-aol-acceptance-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    result["result_json"] = str(result_path)
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", default=os.getenv("PD_UX_E2E_FRONTEND_URL", DEFAULT_FRONTEND_URL))
    parser.add_argument("--api-url", default=os.getenv("PD_UX_E2E_API_URL", DEFAULT_API_URL))
    parser.add_argument("--control-url", default=os.getenv("PD_UX_E2E_CONTROL_URL", DEFAULT_CONTROL_URL))
    parser.add_argument("--owner-user-id", default=os.getenv("PD_UX_E2E_OWNER_USER_ID", DEFAULT_OWNER_USER_ID))
    parser.add_argument("--workspace-id", default=os.getenv("PD_UX_E2E_WORKSPACE_ID"))
    parser.add_argument("--session-id", default=os.getenv("PD_UX_E2E_SESSION_ID"))
    parser.add_argument("--scene-id", default=os.getenv("PD_UX_E2E_SCENE_ID"))
    parser.add_argument("--artifact-id", default=os.getenv("PD_UX_E2E_ARTIFACT_ID"))
    parser.add_argument("--output-dir", default=os.getenv("PD_UX_E2E_OUTPUT_DIR", ".tmp/e2e/pd-ux-aol"))
    parser.add_argument("--timeout-ms", type=int, default=int(os.getenv("PD_UX_E2E_TIMEOUT_MS", "45000")))
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    result = run_acceptance(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
