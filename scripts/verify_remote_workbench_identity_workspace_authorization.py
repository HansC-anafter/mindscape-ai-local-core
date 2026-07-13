#!/usr/bin/env python3
"""Verify and transition Remote Workbench identity-to-workspace authorization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from remote_workbench_authorization_cutover.http import HttpClient
from remote_workbench_authorization_cutover.edge import AccessEdgeGate
from remote_workbench_authorization_cutover.exclusive_lock import phase06_runner_lock
from remote_workbench_authorization_cutover.io import CommandExecutor, CutoverError
from remote_workbench_authorization_cutover.release import ReleaseGate
from remote_workbench_authorization_cutover.remote_ingress import RemoteIngressGate
from remote_workbench_authorization_cutover.repository import lock_phase06_repositories
from remote_workbench_authorization_cutover.resources import RedisResourceSampler
from remote_workbench_authorization_cutover.runtime import RuntimeGate
from remote_workbench_authorization_cutover.claim_gate import RunnerClaimGate
from remote_workbench_authorization_cutover.transition_recovery import (
    safe_close_before_preflight,
)
from remote_workbench_authorization_cutover.workflow import CutoverWorkflow


def build_parser() -> argparse.ArgumentParser:
    """Build the locked cutover/backout command contract."""

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("cutover", "backout"))
    parser.add_argument("--cloud-worktree", type=Path, required=True)
    parser.add_argument("--secure-input-dir", type=Path, required=True)
    parser.add_argument("--target-workspace-id", required=True)
    parser.add_argument("--inheritance-workspace-id", required=True)
    return parser


def main() -> int:
    """Run the requested workflow and emit only a sanitized terminal summary."""

    args = build_parser().parse_args()
    try:
        with phase06_runner_lock():
            return _run_locked(args)
    except CutoverError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


def _run_locked(args: argparse.Namespace) -> int:
    """Run every repository and runtime action while the host lock is held."""

    executor = CommandExecutor()
    script_repo_root = Path(__file__).resolve().parents[1]
    preflight_runtime = RuntimeGate(
        repo_root=script_repo_root,
        executor=executor,
        http=HttpClient(),
    )
    safe_close_before_preflight(
        args.secure_input_dir,
        preflight_runtime,
    )
    try:
        repositories = lock_phase06_repositories(
            script_repo_root=script_repo_root,
            runner_cwd=Path.cwd(),
            cloud_worktree=args.cloud_worktree,
            executor=executor,
            python_prefix=Path(sys.prefix),
        )
    except CutoverError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    repo_root = repositories.canonical_local
    http = HttpClient()
    runtime = RuntimeGate(repo_root=repo_root, executor=executor, http=http)
    resources = RedisResourceSampler(executor)
    workflow = CutoverWorkflow(
        edge=AccessEdgeGate(http),
        ingress=RemoteIngressGate(http),
        release=ReleaseGate(
            repo_root=repo_root,
            cloud_worktree=repositories.canonical_cloud,
            executor=executor,
            http=http,
        ),
        runtime=runtime,
        resources=resources,
        claims=RunnerClaimGate(http=http, resources=resources),
    )
    try:
        if args.action == "cutover":
            result = workflow.cutover(
                secure_input_dir=args.secure_input_dir,
                target_workspace_id=args.target_workspace_id,
                inheritance_workspace_id=args.inheritance_workspace_id,
            )
        else:
            result = workflow.backout(
                secure_input_dir=args.secure_input_dir,
                target_workspace_id=args.target_workspace_id,
                inheritance_workspace_id=args.inheritance_workspace_id,
            )
    except CutoverError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR: Authorization runner failed closed", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
