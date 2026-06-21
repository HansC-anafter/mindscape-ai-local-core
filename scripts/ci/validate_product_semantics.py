#!/usr/bin/env python3
"""Validate product semantic guardrails for Local Core changes."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

try:
    from product_semantic_traceability import (
        surface_ids,
        validate_contract_traceability,
        validate_preflight_declaration,
    )
except ModuleNotFoundError:
    from scripts.ci.product_semantic_traceability import (
        surface_ids,
        validate_contract_traceability,
        validate_preflight_declaration,
    )


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = DEFAULT_REPO_ROOT / "ci" / "product_semantic_surfaces.yaml"
DEFAULT_WORKFLOW_PATH = ".github/workflows/architecture-guardrails.yml"
ZERO_SHA = "0" * 40
WORKFLOW_EVENTS = ("pull_request", "push")

SEMANTIC_DECLARATION_RE = re.compile(
    r"product-semantic-change:\s*(none|approved)\b",
    re.IGNORECASE,
)
DECISION_RECORD_RE = re.compile(
    r"semantic-decision-record:\s*(\S+)",
    re.IGNORECASE,
)
APPROVER_RE = re.compile(
    r"breaking-product-semantics-approved-by:\s*(\S+)",
    re.IGNORECASE,
)


def _normalize_path(value: str | Path) -> str:
    normalized = str(value).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _matches_any(path: str | Path, patterns: list[str]) -> bool:
    normalized = _normalize_path(path)
    pure = PurePosixPath(normalized)
    for pattern in patterns:
        candidate = pattern.strip()
        if not candidate:
            continue
        if pure.match(candidate) or fnmatch(normalized, candidate):
            return True
    return False


def _run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def _changed_files(repo_root: Path, base_sha: str, head_sha: str) -> set[str]:
    if not base_sha or base_sha == ZERO_SHA:
        raise ValueError("base SHA must be provided for product semantic validation")
    output = _run_git(repo_root, ["diff", "--name-only", f"{base_sha}...{head_sha}"])
    return {_normalize_path(line) for line in output.splitlines() if line.strip()}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _load_registry(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"registry is not a mapping: {path}")
    return data


def _load_workflow_paths(path: Path) -> dict[str, list[str]]:
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if not isinstance(data, dict):
        raise ValueError(f"workflow is not a mapping: {path}")
    on_config = data.get("on")
    if not isinstance(on_config, dict):
        raise ValueError(f"workflow `on` section is not a mapping: {path}")
    event_paths: dict[str, list[str]] = {}
    for event_name in WORKFLOW_EVENTS:
        event_config = on_config.get(event_name)
        if event_config is None:
            event_paths[event_name] = []
            continue
        if not isinstance(event_config, dict):
            event_paths[event_name] = ["**"]
            continue
        paths = event_config.get("paths")
        if paths is None:
            event_paths[event_name] = ["**"]
            continue
        if not isinstance(paths, list):
            raise ValueError(f"workflow {event_name}.paths must be a list: {path}")
        event_paths[event_name] = [
            _normalize_path(str(item)) for item in paths if str(item).strip()
        ]
    return event_paths


def _representative_path(pattern: str) -> str:
    sample = _normalize_path(pattern.strip().strip("'\""))
    if sample.endswith("/**"):
        sample = f"{sample[:-3]}/sample"
    sample = sample.replace("**", "sample/nested")
    sample = sample.replace("*", "sample")
    sample = sample.replace("?", "x")
    sample = re.sub(r"\[[^]]+\]", "x", sample)
    return sample.rstrip("/") or "sample"


def _registry_errors(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("version") != 1:
        errors.append("registry.version must be 1")
    declaration = registry.get("declaration")
    if not isinstance(declaration, dict):
        errors.append("registry.declaration must be a mapping")
    else:
        if declaration.get("required_marker") != "product-semantic-change":
            errors.append("declaration.required_marker must be product-semantic-change")
        approval_fields = declaration.get("approval_fields")
        if not isinstance(approval_fields, list) or not approval_fields:
            errors.append("declaration.approval_fields must be a non-empty list")
    surfaces = registry.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        errors.append("registry.surfaces must be a non-empty list")
        return errors
    seen_ids: set[str] = set()
    for index, surface in enumerate(surfaces):
        if not isinstance(surface, dict):
            errors.append(f"surface[{index}] must be a mapping")
            continue
        surface_id = str(surface.get("id") or "")
        if not surface_id:
            errors.append(f"surface[{index}] missing id")
        elif surface_id in seen_ids:
            errors.append(f"duplicate surface id: {surface_id}")
        seen_ids.add(surface_id)
        if surface.get("tier") not in {"P0", "P1", "P2"}:
            errors.append(f"{surface_id}: tier must be P0, P1, or P2")
        if not surface.get("owner"):
            errors.append(f"{surface_id}: owner is required")
        if not surface.get("contract_doc"):
            errors.append(f"{surface_id}: contract_doc is required")
        path_globs = surface.get("path_globs")
        if not isinstance(path_globs, list) or not all(
            isinstance(item, str) and item.strip() for item in path_globs
        ):
            errors.append(f"{surface_id}: path_globs must be a non-empty string list")
        for assertion in surface.get("content_assertions", []) or []:
            if not isinstance(assertion, dict):
                errors.append(f"{surface_id}: content assertion must be a mapping")
                continue
            if not assertion.get("path"):
                errors.append(f"{surface_id}: content assertion missing path")
    return errors


def _registered_surface_hits(
    *,
    registry: dict[str, Any],
    changed_files: set[str],
) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for surface in registry.get("surfaces", []):
        if not surface.get("requires_product_semantic_declaration", True):
            continue
        surface_id = str(surface.get("id"))
        patterns = list(surface.get("path_globs") or [])
        for changed_file in changed_files:
            if _matches_any(changed_file, patterns):
                hits.append((surface_id, changed_file))
    return sorted(set(hits), key=lambda item: (item[0], item[1]))


def _assertion_token(item: Any) -> tuple[str, str | None]:
    if isinstance(item, str):
        return item, None
    if isinstance(item, dict):
        return str(item.get("token") or ""), item.get("message")
    return "", None


def _validate_content_assertions(
    *,
    repo_root: Path,
    registry: dict[str, Any],
    errors: list[str],
) -> None:
    for surface in registry.get("surfaces", []):
        surface_id = str(surface.get("id") or "unknown-surface")
        for assertion in surface.get("content_assertions", []) or []:
            relative_path = _normalize_path(assertion.get("path") or "")
            if not relative_path:
                continue
            source = _read_text(repo_root / relative_path)
            if not source:
                continue
            for item in assertion.get("forbidden_text", []) or []:
                token, message = _assertion_token(item)
                if token and token in source:
                    errors.append(
                        f"{relative_path} [{surface_id}]: "
                        f"{message or f'forbidden text present: {token}'}"
                    )
            for item in assertion.get("required_text", []) or []:
                token, message = _assertion_token(item)
                if token and token not in source:
                    errors.append(
                        f"{relative_path} [{surface_id}]: "
                        f"{message or f'required text missing: {token}'}"
                    )


def _validate_workflow_path_coverage(
    *,
    registry: dict[str, Any],
    workflow_path: Path,
    workflow_relative_path: str,
    errors: list[str],
) -> None:
    try:
        workflow_paths = _load_workflow_paths(workflow_path)
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
        return
    for surface in registry.get("surfaces", []):
        if not surface.get("requires_product_semantic_declaration", True):
            continue
        surface_id = str(surface.get("id") or "unknown-surface")
        for pattern in surface.get("path_globs", []) or []:
            representative = _representative_path(str(pattern))
            for event_name in WORKFLOW_EVENTS:
                event_patterns = workflow_paths.get(event_name, [])
                if not _matches_any(representative, event_patterns):
                    errors.append(
                        f"{workflow_relative_path} [{surface_id}]: "
                        f"{event_name} paths do not cover registry path_glob "
                        f"`{pattern}` (sample `{representative}`)."
                    )


def _validate_pr_declaration(
    *,
    registry: dict[str, Any],
    event_name: str,
    changed_files: set[str],
    pr_body_file: Path | None,
    errors: list[str],
) -> None:
    if event_name != "pull_request":
        return
    surface_hits = _registered_surface_hits(
        registry=registry,
        changed_files=changed_files,
    )
    if not surface_hits:
        return
    if pr_body_file is None:
        errors.append(
            "Product semantic declaration is required for protected product "
            "semantic paths, but no PR body file was provided."
        )
        return
    body = _read_text(pr_body_file)
    declaration = SEMANTIC_DECLARATION_RE.search(body)
    if declaration is None:
        errors.append(
            "PR touches protected product semantic paths but does not declare "
            "`product-semantic-change: none` or `product-semantic-change: approved`."
        )
        errors.append(
            "Protected product semantic changes: "
            + ", ".join(f"{surface_id}:{path}" for surface_id, path in surface_hits)
        )
        return
    semantic_change = declaration.group(1).lower()
    validate_preflight_declaration(
        body=body,
        semantic_change=semantic_change,
        expected_surface_ids=surface_ids(surface_hits),
        errors=errors,
    )
    if semantic_change != "approved":
        return
    if DECISION_RECORD_RE.search(body) is None:
        errors.append(
            "Approved product semantic changes require `semantic-decision-record: <path>`."
        )
    if APPROVER_RE.search(body) is None:
        errors.append(
            "Approved breaking product semantic changes require "
            "`breaking-product-semantics-approved-by: <owner>`."
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", default="push")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--pr-body-file")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--workflow-path", default=DEFAULT_WORKFLOW_PATH)
    parser.add_argument("--changed-files-file")
    parser.add_argument("--contract-root")
    parser.add_argument("--validate-registry-only", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    contract_root = Path(args.contract_root).resolve() if args.contract_root else None
    registry_path = Path(args.registry).resolve()
    workflow_arg = Path(args.workflow_path)
    workflow_path = workflow_arg if workflow_arg.is_absolute() else repo_root / workflow_arg
    workflow_relative_path = _normalize_path(
        workflow_path.relative_to(repo_root) if workflow_path.is_relative_to(repo_root) else workflow_path
    )
    registry = _load_registry(registry_path)
    errors: list[str] = []
    errors.extend(_registry_errors(registry))
    validate_contract_traceability(
        repo_root=repo_root,
        registry=registry,
        contract_root=contract_root,
        errors=errors,
    )
    if errors:
        print("Product semantic registry is invalid:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if args.validate_registry_only:
        print("Product semantic registry is valid")
        return 0

    if args.changed_files_file:
        changed = {
            _normalize_path(line)
            for line in Path(args.changed_files_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    else:
        changed = _changed_files(repo_root, args.base_sha, args.head_sha)
    _validate_content_assertions(
        repo_root=repo_root,
        registry=registry,
        errors=errors,
    )
    _validate_workflow_path_coverage(
        registry=registry,
        workflow_path=workflow_path,
        workflow_relative_path=workflow_relative_path,
        errors=errors,
    )
    _validate_pr_declaration(
        registry=registry,
        event_name=args.event_name,
        changed_files=changed,
        pr_body_file=Path(args.pr_body_file) if args.pr_body_file else None,
        errors=errors,
    )

    if errors:
        print("Product semantic guardrail failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Product semantic guardrail passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
