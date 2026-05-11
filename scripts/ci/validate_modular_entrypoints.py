#!/usr/bin/env python3
"""
Validate that risky changes open a modular entrypoint or provide a narrow PR-only exception.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
ZERO_SHA = "0" * 40


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    additions: int
    deletions: int

    @property
    def changed_lines(self) -> int:
        return self.additions + self.deletions

    @property
    def is_new(self) -> bool:
        return self.status == "A"


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


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def _matches_any(path: str, patterns: list[str]) -> bool:
    normalized = _normalize_path(path)
    pure = PurePosixPath(normalized)
    for pattern in patterns:
        candidate = pattern.strip()
        if not candidate:
            continue
        if pure.match(candidate) or fnmatch(normalized, candidate):
            return True
    return False


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


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


def _read_changed_files(repo_root: Path, base_sha: str, head_sha: str) -> list[ChangedFile]:
    name_status = _git(repo_root, "diff", "--name-status", "--find-renames", base_sha, head_sha)
    numstats = _parse_numstats(
        _git(repo_root, "diff", "--numstat", "--find-renames", base_sha, head_sha)
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


def _line_count(repo_root: Path, relative_path: str) -> int:
    target = repo_root / relative_path
    if not target.exists() or not target.is_file():
        return 0
    return len(_read_text(target).splitlines())


def _collect_cross_surface_hits(
    changed_files: list[ChangedFile], policy: dict[str, Any]
) -> list[tuple[str, list[str]]]:
    hits: list[tuple[str, list[str]]] = []
    for group in policy.get("multi_surface_groups", []):
        surfaces = group.get("surfaces", {})
        matched: list[str] = []
        for surface_name, patterns in surfaces.items():
            if any(_matches_any(item.path, patterns) for item in changed_files):
                matched.append(surface_name)
        if len(matched) > 1:
            hits.append((group.get("name", "unnamed-group"), matched))
    return hits


def _detect_seam_candidates(
    changed_files: list[ChangedFile], policy: dict[str, Any]
) -> list[str]:
    seam_policy = policy.get("accepted_seam_markers", {})
    fragments = [item.lower() for item in seam_policy.get("file_name_fragments", [])]
    suffixes = set(seam_policy.get("code_suffixes", [".py"]))

    candidates: list[str] = []
    for item in changed_files:
        normalized = _normalize_path(item.path)
        suffix = Path(normalized).suffix.lower()
        if suffix not in suffixes:
            continue
        file_name = Path(normalized).name.lower()
        parts = [part.lower() for part in PurePosixPath(normalized).parts]
        if any(fragment in file_name for fragment in fragments) or any(
            part in fragments for part in parts
        ):
            candidates.append(normalized)
    return candidates


def _validate_exception_body(policy: dict[str, Any], body: str) -> tuple[bool, list[str]]:
    markers = policy.get("exception_markers", {})
    claim_markers = [item.lower() for item in markers.get("claim_markers", [])]
    required_fields = markers.get("required_fields", [])

    lowered = body.lower()
    claim_found = False
    for marker in claim_markers:
        if f"[x] {marker}" in lowered or f"{marker}: yes" in lowered or f"{marker}: true" in lowered:
            claim_found = True
            break

    missing: list[str] = []
    if not claim_found:
        missing.append("missing checked leaf-only exception claim")

    for field in required_fields:
        pattern = re.compile(rf"{re.escape(field)}\s*:\s*(.+)", re.IGNORECASE)
        match = pattern.search(body)
        if not match or not match.group(1).strip():
            missing.append(f"missing exception field: {field}")

    return not missing, missing


def evaluate_modular_entry_guard(
    *,
    repo_root: Path,
    policy: dict[str, Any],
    changed_files: list[ChangedFile],
    event_name: str,
    pr_body: str,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    high_risk_paths = policy.get("high_risk_paths", [])
    protected_entries = policy.get("protected_monoliths", [])
    event_rules = policy.get("event_rules", {}).get(event_name, {})
    large_file_line_threshold = int(policy.get("large_file_line_threshold", 500))
    large_file_changed_lines_threshold = int(policy.get("large_file_changed_lines_threshold", 20))

    cross_surface_hits = _collect_cross_surface_hits(changed_files, policy)
    if cross_surface_hits:
        for group_name, surfaces in cross_surface_hits:
            reasons.append(
                f"cross-surface change in {group_name}: {', '.join(sorted(surfaces))}"
            )

    protected_hits: list[str] = []
    protected_paths: list[str] = []
    for entry in protected_entries:
        target_path = entry["path"]
        diff_budget = int(entry.get("diff_budget", large_file_changed_lines_threshold))
        for item in changed_files:
            if _normalize_path(item.path) != _normalize_path(target_path):
                continue
            if item.changed_lines > diff_budget:
                protected_hits.append(
                    f"protected monolith exceeded diff budget: {item.path} ({item.changed_lines}>{diff_budget})"
                )
                protected_paths.append(item.path)
    reasons.extend(protected_hits)

    for item in changed_files:
        if not _matches_any(item.path, high_risk_paths):
            continue
        line_count = _line_count(repo_root, item.path)
        if line_count >= large_file_line_threshold and item.changed_lines > large_file_changed_lines_threshold:
            reasons.append(
                f"large high-risk file changed above threshold: {item.path} ({line_count} lines, {item.changed_lines} changed lines)"
            )

    if not reasons:
        return True, ["no risky changes detected"]

    seam_candidates = _detect_seam_candidates(changed_files, policy)
    if seam_candidates:
        if protected_paths:
            missing_handoff: list[str] = []
            seam_tokens = [Path(path).stem.lower() for path in seam_candidates]
            for protected_path in protected_paths:
                content_path = repo_root / protected_path
                content = _read_text(content_path).lower() if content_path.exists() else ""
                if not any(token in content for token in seam_tokens):
                    missing_handoff.append(protected_path)
            if not missing_handoff:
                return True, [
                    *reasons,
                    f"seam evidence detected via {', '.join(sorted(seam_candidates))}",
                ]
        else:
            return True, [
                *reasons,
                f"seam evidence detected via {', '.join(sorted(seam_candidates))}",
            ]

    if event_rules.get("allow_leaf_only_exception"):
        is_valid_exception, exception_errors = _validate_exception_body(policy, pr_body)
        if is_valid_exception:
            return True, [*reasons, "valid leaf-only exception provided"]
        reasons.extend(exception_errors)
    else:
        reasons.append("leaf-only exceptions are not allowed for this event")

    reasons.append("missing modular entrypoint evidence")
    return False, reasons


def main() -> int:
    args = _parse_args()
    repo_root = Path(args.repo_root).resolve()
    policy_path = Path(args.policy).resolve()

    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 1

    base_sha = args.base_sha
    head_sha = args.head_sha
    if not base_sha or base_sha == ZERO_SHA:
        print("ERROR: base SHA must be provided for modular entry validation")
        return 1

    policy = _load_yaml(policy_path)
    changed_files = _read_changed_files(repo_root, base_sha, head_sha)
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
