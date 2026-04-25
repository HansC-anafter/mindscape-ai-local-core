#!/usr/bin/env python3

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.app.services.e2e.meeting_spatial_downstream_e2e import (  # noqa: E402
    run_meeting_spatial_downstream_e2e,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Meeting -> spatial -> downstream continuity validator"
    )
    parser.add_argument("--workspace-id", help="Workspace ID to run against")
    parser.add_argument("--profile-id", help="Profile ID (default: default-user)")
    parser.add_argument("--thread-id", help="Thread ID (auto-create if absent)")
    parser.add_argument("--project-id", help="Project ID (optional)")
    parser.add_argument(
        "--scenario-file",
        type=Path,
        required=True,
        help="Markdown scenario file with ```e2e_config``` block",
    )
    parser.add_argument(
        "--meeting-session-id",
        help="Reuse an existing closed meeting session instead of starting a new one",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for local-core e2e evidence bundle",
    )
    parser.add_argument("--model-name", help="Override model name")
    parser.add_argument(
        "--executor-runtime",
        help="Force meeting generation through an executor runtime (e.g. codex_cli)",
    )
    parser.add_argument(
        "--require-motion-evidence",
        action="store_true",
        help="Fail unless motion asset / clip / keyframe / visual acceptance evidence is materialized",
    )
    parser.add_argument(
        "--emit-visual-acceptance-bundle",
        action="store_true",
        help="Build visual acceptance bundle evidence for this run",
    )
    parser.add_argument("--max-events", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = asyncio.run(
            run_meeting_spatial_downstream_e2e(
                scenario_file=args.scenario_file,
                output_dir=args.output_dir,
                meeting_session_id=args.meeting_session_id,
                workspace_id=args.workspace_id,
                profile_id=args.profile_id,
                thread_id=args.thread_id,
                project_id=args.project_id,
                model_name=args.model_name,
                executor_runtime=args.executor_runtime,
                require_motion_evidence=args.require_motion_evidence,
                emit_visual_acceptance_bundle=args.emit_visual_acceptance_bundle,
                max_events=args.max_events,
            )
        )
    except Exception as exc:
        print(f"Meeting spatial downstream E2E failed: {exc}", file=sys.stderr)
        return 1

    print("Meeting spatial downstream E2E validation passed")
    print(f"- scenario_id: {result['scenario_id']}")
    print(f"- output_dir: {result['output_dir']}")
    print(f"- cloud_output_root: {result['cloud_output_root']}")
    if result.get("meeting_runtime_binding"):
        print(
            f"- executor_runtime: {result['meeting_runtime_binding'].get('runtime_id')}"
            f" ({result['meeting_runtime_binding'].get('transport')})"
        )
    print(
        f"- meeting_session_id: {result['meeting_session_receipt'].get('meeting_session_id')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
