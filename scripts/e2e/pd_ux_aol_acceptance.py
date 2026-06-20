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
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from pd_ux_aol_acceptance_browser import _run_browser_acceptance  # noqa: E402
from pd_ux_aol_acceptance_common import (  # noqa: E402
    DEFAULT_API_URL,
    DEFAULT_CONTROL_URL,
    DEFAULT_FRONTEND_URL,
    DEFAULT_OWNER_USER_ID,
    STAGES,
    _add_check,
    _add_evidence,
    _finalize_stages,
    _first_pd_storyboard_session,
    _first_workspace_id,
    _ignored_failed_request,
    _json_get,
    _json_post,
    _json_request,
    _manifest,
    _manifest_has_kind,
    _project_graph,
    _repo_root,
    _request_failure_text,
    _safe_call,
    _stage_template,
    _storyboard_ref,
    _write_acceptance_result,
)
from pd_ux_aol_acceptance_compilers import (  # noqa: E402
    _compile_director_guidance,
    _compile_human_contribution,
    _compile_runtime_readiness,
    _compile_scene_critique,
)
from pd_ux_aol_acceptance_runner import run_acceptance  # noqa: E402
from pd_ux_aol_acceptance_runtime import (  # noqa: E402
    _bound_runtime_ids,
    _dispatch_meeting_runtime_command,
    _load_codex_quota_preflight_runner,
    _meeting_runtime_evidence,
    _run_codex_quota_preflight,
    _runtime_evidence_ready,
    _runtime_route_evidence,
    _wait_meeting_runtime_evidence,
    _wait_workspace_runtime_available,
    _workspace_agent_statuses,
    _workspace_runtime_state,
)

__all__ = [
    "DEFAULT_API_URL",
    "DEFAULT_CONTROL_URL",
    "DEFAULT_FRONTEND_URL",
    "DEFAULT_OWNER_USER_ID",
    "STAGES",
    "_add_check",
    "_add_evidence",
    "_bound_runtime_ids",
    "_compile_director_guidance",
    "_compile_human_contribution",
    "_compile_runtime_readiness",
    "_compile_scene_critique",
    "_dispatch_meeting_runtime_command",
    "_finalize_stages",
    "_first_pd_storyboard_session",
    "_first_workspace_id",
    "_ignored_failed_request",
    "_json_get",
    "_json_post",
    "_json_request",
    "_load_codex_quota_preflight_runner",
    "_manifest",
    "_manifest_has_kind",
    "_meeting_runtime_evidence",
    "_project_graph",
    "_repo_root",
    "_request_failure_text",
    "_run_browser_acceptance",
    "_run_codex_quota_preflight",
    "_runtime_evidence_ready",
    "_runtime_route_evidence",
    "_safe_call",
    "_stage_template",
    "_storyboard_ref",
    "_wait_meeting_runtime_evidence",
    "_wait_workspace_runtime_available",
    "_workspace_agent_statuses",
    "_workspace_runtime_state",
    "_write_acceptance_result",
    "main",
    "parse_args",
    "run_acceptance",
]


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
    parser.add_argument("--skip-codex-quota-preflight", action="store_true")
    parser.add_argument("--continue-on-codex-quota-failure", action="store_true")
    parser.add_argument(
        "--codex-quota-max-runtime-probes",
        type=int,
        default=int(os.getenv("PD_UX_E2E_CODEX_QUOTA_MAX_RUNTIME_PROBES", "8")),
    )
    parser.add_argument(
        "--codex-quota-timeout-seconds",
        type=float,
        default=float(os.getenv("PD_UX_E2E_CODEX_QUOTA_TIMEOUT_SECONDS", "90")),
    )
    parser.add_argument(
        "--codex-quota-stall-timeout-seconds",
        type=float,
        default=float(os.getenv("PD_UX_E2E_CODEX_QUOTA_STALL_TIMEOUT_SECONDS", "30")),
    )
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    result = run_acceptance(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
