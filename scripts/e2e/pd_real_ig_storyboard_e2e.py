#!/usr/bin/env python3
"""Run the real IG reference PD storyboard E2E and validate content gates."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from pd_real_ig_storyboard_e2e_core import (  # noqa: E402
    DEFAULT_REFS,
    _as_dict,
    _as_list,
    _utc_stamp,
    _write_json,
)
from pd_real_ig_storyboard_e2e_http import (  # noqa: E402
    _TRANSPORT_EXCEPTIONS,
    _fetch_session_and_events,
    _http_json,
    _request_error_payload,
    _safe_fetch_json,
    _session_is_terminal,
    _submit_command_with_recovery_marker,
)
from pd_real_ig_storyboard_e2e_payloads import (  # noqa: E402
    _build_envelope,
    _build_start_body,
    _quality_requirements,
)
from pd_real_ig_storyboard_e2e_runtime import (  # noqa: E402
    _run_quota_preflight,
    run_e2e,
)
from pd_real_ig_storyboard_e2e_validation import (  # noqa: E402
    _collect_existing_paths,
    _copy_artifacts,
    _duration_sum,
    _find_quality_gate_summaries,
    _find_reference_cue_maps,
    _find_scene_judges,
    _find_storyboards,
    _iter_nodes,
    _quota_evidence_summary,
    _runtime_evidence_mentions_managed_provider,
    _runtime_evidence_uses_codex_workspace,
    _scene_has_any,
    _scene_id,
    _scene_score_id,
    _schema_payloads,
    _score_axis_passed,
    _text_blob,
    _validate,
)

__all__ = [
    "DEFAULT_REFS",
    "_TRANSPORT_EXCEPTIONS",
    "_as_dict",
    "_as_list",
    "_build_envelope",
    "_build_start_body",
    "_collect_existing_paths",
    "_copy_artifacts",
    "_duration_sum",
    "_fetch_session_and_events",
    "_find_quality_gate_summaries",
    "_find_reference_cue_maps",
    "_find_scene_judges",
    "_find_storyboards",
    "_http_json",
    "_iter_nodes",
    "_quality_requirements",
    "_quota_evidence_summary",
    "_request_error_payload",
    "_run_quota_preflight",
    "_runtime_evidence_mentions_managed_provider",
    "_runtime_evidence_uses_codex_workspace",
    "_safe_fetch_json",
    "_scene_has_any",
    "_scene_id",
    "_scene_score_id",
    "_schema_payloads",
    "_score_axis_passed",
    "_session_is_terminal",
    "_submit_command_with_recovery_marker",
    "_text_blob",
    "_utc_stamp",
    "_validate",
    "_write_json",
    "parse_args",
    "run",
]


def run(args: argparse.Namespace) -> dict:
    return run_e2e(
        args,
        http_json=_http_json,
        quota_preflight=_run_quota_preflight,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8200")
    parser.add_argument("--workspace-id", default="bac7ce63-e768-454d-96f3-3a00e8e1df69")
    parser.add_argument("--project-id", default="content_campaign_20251215_134931_c9b794db")
    parser.add_argument("--lens-id", default="9f9f6262-8fc4-421e-8835-66474af69eb9")
    parser.add_argument("--thread-id", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--command-id", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--reference-ids", default=",".join(DEFAULT_REFS))
    parser.add_argument("--target-duration-sec", type=int, default=90)
    parser.add_argument("--duration-tolerance-sec", type=float, default=4.0)
    parser.add_argument("--scene-count-target", type=int, default=45)
    parser.add_argument("--scene-count-floor", type=int, default=40)
    parser.add_argument("--max-rounds", type=int, default=1)
    parser.add_argument("--http-timeout-seconds", type=int, default=120)
    parser.add_argument("--command-timeout-seconds", type=int, default=1200)
    parser.add_argument("--post-command-poll-seconds", type=int, default=900)
    parser.add_argument("--post-command-poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--skip-quota-preflight", action="store_true")
    parser.add_argument("--codex-quota-max-runtime-probes", type=int, default=4)
    parser.add_argument("--codex-quota-target-successes", type=int, default=2)
    parser.add_argument("--codex-quota-timeout-seconds", type=int, default=90)
    parser.add_argument("--codex-quota-stall-timeout-seconds", type=int, default=30)
    parser.add_argument(
        "--required-codex-login-email",
        default=os.environ.get("PD_E2E_REQUIRED_CODEX_LOGIN_EMAIL", ""),
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        result = run(parse_args())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result.get("status") == "passed" else 2)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        raise
