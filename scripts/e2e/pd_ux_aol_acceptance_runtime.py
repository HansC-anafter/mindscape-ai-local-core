"""Runtime and quota helpers for the PD UX AOL acceptance runner."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from pd_ux_aol_acceptance_common import _json_get, _json_post


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


def _load_codex_quota_preflight_runner() -> Callable[[argparse.Namespace], Any]:
    module_path = Path(__file__).with_name("codex_pool_quota_preflight.py")
    spec = importlib.util.spec_from_file_location(
        "mindscape_codex_pool_quota_preflight",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Codex quota preflight from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runner = getattr(module, "run_preflight", None)
    if not callable(runner):
        raise RuntimeError("Codex quota preflight runner is unavailable")
    return runner


def _run_codex_quota_preflight(
    args: argparse.Namespace,
    workspace_id: str,
) -> dict[str, Any]:
    if args.skip_codex_quota_preflight:
        return {
            "status": "skipped",
            "reason": "skip_codex_quota_preflight",
            "workspace_id": workspace_id,
        }
    runner = _load_codex_quota_preflight_runner()
    preflight_args = argparse.Namespace(
        workspace_id=workspace_id,
        max_runtime_probes=args.codex_quota_max_runtime_probes,
        timeout_seconds=args.codex_quota_timeout_seconds,
        stall_timeout_seconds=args.codex_quota_stall_timeout_seconds,
        required_login_email="",
        exclude_runtime_id=[],
        target_successes=1,
        continue_after_success=False,
        compact_output=False,
    )
    return asyncio.run(runner(preflight_args))


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
        "native_spatial_source": metadata.get("native_spatial_source"),
        "native_spatial_decision_present": bool(metadata.get("native_spatial_decision")),
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
