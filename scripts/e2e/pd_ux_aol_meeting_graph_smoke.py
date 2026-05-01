#!/usr/bin/env python3
"""Browser smoke for PD UX AOL meeting / graph shell flow.

This intentionally uses the repo's Python Playwright runtime instead of adding
web-console npm dependencies. It validates the live installed UI path:

PD session route -> AOL scene selection -> role-bearing attach -> meeting shell.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_FRONTEND_URL = "http://127.0.0.1:8300"
DEFAULT_API_URL = "http://127.0.0.1:8200"
DEFAULT_OWNER_USER_ID = "default-user"


def _json_get(url: str, *, timeout: float = 15.0) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GET {url} failed: {exc}") from exc
    return json.loads(body)


def _first_workspace_id(api_url: str, owner_user_id: str) -> str:
    payload = _json_get(
        f"{api_url.rstrip('/')}/api/v1/workspaces?owner_user_id={owner_user_id}"
    )
    workspaces = payload if isinstance(payload, list) else payload.get("workspaces", [])
    for workspace in workspaces:
        workspace_id = str(workspace.get("id") or "").strip()
        if workspace_id:
            return workspace_id
    raise RuntimeError(f"No workspace found for owner_user_id={owner_user_id!r}")


def _first_pd_storyboard_session(api_url: str, workspace_id: str) -> tuple[str, str]:
    payload = _json_get(
        f"{api_url.rstrip('/')}/api/v1/capabilities/performance_direction/sessions"
        f"?workspace_id={workspace_id}&limit=10"
    )
    sessions = payload.get("sessions", []) if isinstance(payload, dict) else []
    for session in sessions:
        session_id = str(session.get("session_id") or "").strip()
        summary = session.get("storyboard_summary") or {}
        scene_ids = summary.get("scene_ids") or []
        if session_id and scene_ids:
            return session_id, str(scene_ids[0])
    raise RuntimeError(f"No PD storyboard session found for workspace_id={workspace_id!r}")


def _write_artifact(output_dir: Path, name: str, data: bytes) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / name
    path.write_bytes(data)
    return path


def _request_failure_text(request: Any) -> str:
    failure = request.failure
    if callable(failure):
        failure = failure()
    return str(failure or "")


def _is_ignored_failed_request(request: Any) -> bool:
    failure = _request_failure_text(request)
    # Closing Chromium can abort an in-flight background poll after the smoke
    # assertions have passed. Keep genuine network failures visible.
    return failure == "net::ERR_ABORTED" and "/api/v1/cloud-sync/status" in request.url


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    api_url = args.api_url.rstrip("/")
    frontend_url = args.frontend_url.rstrip("/")
    workspace_id = args.workspace_id or _first_workspace_id(api_url, args.owner_user_id)

    if args.session_id and args.scene_id:
        session_id = args.session_id
        scene_id = args.scene_id
    else:
        session_id, scene_id = _first_pd_storyboard_session(api_url, workspace_id)
        session_id = args.session_id or session_id
        scene_id = args.scene_id or scene_id

    session_url = (
        f"{frontend_url}/workspaces/{workspace_id}"
        f"/capabilities/performance_direction/sessions/{session_id}"
    )
    scene_selector = f'[data-testid="pd-aol-scene-{scene_id}"]'
    output_dir = Path(args.output_dir)

    started = time.time()
    console_errors: list[str] = []
    failed_requests: list[str] = []

    def record_failed_request(request: Any) -> None:
        if _is_ignored_failed_request(request):
            return
        failed_requests.append(
            f"{request.method} {request.url} :: {_request_failure_text(request)}"
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={"width": 1440, "height": 1600})
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text)
            if msg.type in {"error", "warning"} and "baseline-browser-mapping" not in msg.text
            else None,
        )
        page.on("requestfailed", record_failed_request)

        page.goto(session_url, wait_until="commit", timeout=args.timeout_ms)
        page.wait_for_selector('[data-testid="aol-global-anchor"]', timeout=args.timeout_ms)
        page.wait_for_selector(scene_selector, timeout=args.timeout_ms)

        page.locator('[data-testid="aol-global-anchor"]').click(timeout=5_000)
        page.get_by_text("Select an object on this page").wait_for(timeout=10_000)
        page.locator(scene_selector).click(timeout=10_000, force=True)

        page.wait_for_selector('[data-testid="aol-host-panel"]', timeout=args.timeout_ms)
        page.wait_for_selector('[data-testid="aol-role-control"]', timeout=args.timeout_ms)
        page.locator('[data-testid="aol-role-option-target"]').click(timeout=5_000)

        panel_text = page.locator('[data-testid="aol-host-panel"]').inner_text(timeout=10_000)
        if "storyboard_scene" not in panel_text or "Target" not in panel_text:
            raise AssertionError(f"Unexpected AOL host panel text: {panel_text[:1000]}")

        page.get_by_role("button", name="Open Meeting").click(timeout=10_000)
        page.wait_for_selector('[data-testid="aol-meeting-pane"]', timeout=args.timeout_ms)
        page.wait_for_selector('[data-testid="aol-meeting-bottom-shell"]', timeout=args.timeout_ms)

        screenshot_path = _write_artifact(
            output_dir,
            "pd-ux-aol-meeting-graph-smoke.png",
            page.screenshot(full_page=True),
        )
        browser.close()

    return {
        "status": "passed",
        "workspace_id": workspace_id,
        "session_id": session_id,
        "scene_id": scene_id,
        "session_url": session_url,
        "duration_ms": round((time.time() - started) * 1000),
        "screenshot": str(screenshot_path),
        "console_errors": console_errors,
        "failed_requests": failed_requests,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", default=os.getenv("PD_UX_E2E_FRONTEND_URL", DEFAULT_FRONTEND_URL))
    parser.add_argument("--api-url", default=os.getenv("PD_UX_E2E_API_URL", DEFAULT_API_URL))
    parser.add_argument("--owner-user-id", default=os.getenv("PD_UX_E2E_OWNER_USER_ID", DEFAULT_OWNER_USER_ID))
    parser.add_argument("--workspace-id", default=os.getenv("PD_UX_E2E_WORKSPACE_ID"))
    parser.add_argument("--session-id", default=os.getenv("PD_UX_E2E_SESSION_ID"))
    parser.add_argument("--scene-id", default=os.getenv("PD_UX_E2E_SCENE_ID"))
    parser.add_argument("--output-dir", default=os.getenv("PD_UX_E2E_OUTPUT_DIR", ".tmp/e2e/pd-ux-aol"))
    parser.add_argument("--timeout-ms", type=int, default=int(os.getenv("PD_UX_E2E_TIMEOUT_MS", "45000")))
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    result = run_smoke(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
