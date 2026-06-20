"""Playwright browser acceptance flow for PD UX AOL checks."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from pd_ux_aol_acceptance_common import (
    _add_check,
    _ignored_failed_request,
    _json_get,
    _request_failure_text,
    _safe_call,
)
from pd_ux_aol_acceptance_runtime import (
    _dispatch_meeting_runtime_command,
    _meeting_runtime_evidence,
    _runtime_route_evidence,
    _wait_meeting_runtime_evidence,
    _wait_workspace_runtime_available,
    _workspace_agent_statuses,
    _workspace_runtime_state,
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
                _add_check(
                    stages,
                    "S7",
                    "Meeting command does not enter native spatial shortcut",
                    not runtime_evidence.get("native_spatial_source")
                    and not runtime_evidence.get("native_spatial_decision_present"),
                    evidence={
                        "native_spatial_source": runtime_evidence.get(
                            "native_spatial_source"
                        ),
                        "native_spatial_decision_present": runtime_evidence.get(
                            "native_spatial_decision_present"
                        ),
                    },
                    failure="Meeting command was handled by the native spatial shortcut",
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
