"""Common helpers for the PD UX AOL acceptance runner."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import yaml


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
        stage["passed"] = (
            bool(checks) and all(check["passed"] for check in checks) and not stage["failures"]
        )


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
    manifest_path = (
        _repo_root()
        / "backend"
        / "app"
        / "capabilities"
        / "performance_direction"
        / "manifest.yaml"
    )
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


def _write_acceptance_result(
    *,
    started: float,
    output_dir: Path,
    stages: dict[str, dict[str, Any]],
    workspace_id: str,
    session_id: str,
    scene_id: str,
    artifact_id: str,
    project_id: str | None,
    object_ref: dict[str, Any],
    browser_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
