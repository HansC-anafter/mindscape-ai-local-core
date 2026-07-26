#!/usr/bin/env python3
"""Canonical CLI for modular entry guard validation."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

import yaml

if __package__:
    from .modular_entry_guard_facade import (
        ChangedFile,
        _matches_any,
        _normalize_path,
        evaluate_modular_entry_guard,
    )
else:
    from modular_entry_guard_facade import (
        ChangedFile,
        _matches_any,
        _normalize_path,
        evaluate_modular_entry_guard,
    )


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
ZERO_SHA = "0" * 40


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--pr-body-file")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--changed-files-file")
    return parser.parse_args()


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"policy is not a mapping: {path}")
    return data


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _parse_numstats(raw: str) -> dict[str, tuple[int, int]]:
    stats: dict[str, tuple[int, int]] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        additions, deletions, path = line.split("\t", 2)
        add_value = int(additions) if additions.isdigit() else 0
        del_value = int(deletions) if deletions.isdigit() else 0
        stats[_normalize_path(path)] = (add_value, del_value)
    return stats


def _read_changed_files(
    repo_root: Path,
    base_sha: str,
    head_sha: str,
) -> list[ChangedFile]:
    name_status = _git(
        repo_root,
        "diff",
        "--name-status",
        "--find-renames",
        base_sha,
        head_sha,
    )
    numstats = _parse_numstats(
        _git(
            repo_root,
            "diff",
            "--numstat",
            "--find-renames",
            base_sha,
            head_sha,
        )
    )

    changed: list[ChangedFile] = []
    for line in name_status.splitlines():
        if not line.strip():
            continue
        status, *paths = line.split("\t")
        raw_path = paths[-1]
        path = _normalize_path(raw_path)
        additions, deletions = numstats.get(path, (0, 0))
        changed.append(
            ChangedFile(
                path=path,
                status=status[0],
                additions=additions,
                deletions=deletions,
            )
        )
    return changed


def main() -> int:
    args = _parse_args()
    repo_root = Path(args.repo_root).resolve()
    policy_path = Path(args.policy).resolve()

    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 1
    if not args.base_sha or args.base_sha == ZERO_SHA:
        print("ERROR: base SHA must be provided for modular entry validation")
        return 1

    policy = _load_yaml(policy_path)
    changed_files = _read_changed_files(
        repo_root,
        args.base_sha,
        args.head_sha,
    )
    if not changed_files:
        print("OK: no changed files detected for modular entry validation")
        return 0

    pr_body = ""
    if args.pr_body_file:
        pr_body = Path(args.pr_body_file).read_text(encoding="utf-8")

    is_valid, messages = evaluate_modular_entry_guard(
        repo_root=repo_root,
        policy=policy,
        changed_files=changed_files,
        event_name=args.event_name,
        pr_body=pr_body,
    )

    if is_valid:
        print("OK: modular entry guard passed")
        for message in messages:
            print(f"  - {message}")
        return 0

    print("ERROR: modular entry guard failed")
    for message in messages:
        print(f"  - {message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
