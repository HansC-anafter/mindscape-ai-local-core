"""Policy evaluation facade for the modular entry guard."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
PLACEHOLDER_VALUES = {"-", "n/a", "na", "none", "todo", "tbd"}


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


@dataclass(frozen=True)
class RiskFinding:
    kind: str
    message: str
    affected_paths: tuple[str, ...]


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


def _line_count(repo_root: Path, relative_path: str) -> int:
    target = repo_root / relative_path
    if not target.exists() or not target.is_file():
        return 0
    return len(_read_text(target).splitlines())


def _collect_cross_surface_findings(
    changed_files: list[ChangedFile], policy: dict[str, Any]
) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    for group in policy.get("multi_surface_groups", []):
        surfaces = group.get("surfaces", {})
        matched_surfaces: list[str] = []
        affected_paths: set[str] = set()
        for surface_name, patterns in surfaces.items():
            surface_paths = {
                _normalize_path(item.path)
                for item in changed_files
                if _matches_any(item.path, patterns)
            }
            if surface_paths:
                matched_surfaces.append(surface_name)
                affected_paths.update(surface_paths)
        if len(matched_surfaces) > 1:
            group_name = group.get("name", "unnamed-group")
            message = (
                f"cross-surface change in {group_name}: "
                f"{', '.join(sorted(matched_surfaces))}"
            )
            findings.append(
                RiskFinding(
                    kind="cross-surface",
                    message=message,
                    affected_paths=tuple(sorted(affected_paths)),
                )
            )
    return findings


def _collect_protected_findings(
    changed_files: list[ChangedFile],
    policy: dict[str, Any],
    default_diff_budget: int,
) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    changed_by_path = {
        _normalize_path(item.path): item
        for item in changed_files
    }
    for entry in policy.get("protected_monoliths", []):
        target_path = _normalize_path(entry["path"])
        item = changed_by_path.get(target_path)
        if item is None:
            continue
        diff_budget = int(entry.get("diff_budget", default_diff_budget))
        if item.changed_lines <= diff_budget:
            continue
        findings.append(
            RiskFinding(
                kind="protected-monolith",
                message=(
                    "protected monolith exceeded diff budget: "
                    f"{item.path} ({item.changed_lines}>{diff_budget})"
                ),
                affected_paths=(target_path,),
            )
        )
    return findings


def _collect_large_file_findings(
    repo_root: Path,
    changed_files: list[ChangedFile],
    policy: dict[str, Any],
    line_threshold: int,
    changed_lines_threshold: int,
) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    high_risk_paths = policy.get("high_risk_paths", [])
    for item in changed_files:
        normalized = _normalize_path(item.path)
        if not _matches_any(normalized, high_risk_paths):
            continue
        line_count = _line_count(repo_root, normalized)
        if line_count < line_threshold or item.changed_lines <= changed_lines_threshold:
            continue
        findings.append(
            RiskFinding(
                kind="large-high-risk",
                message=(
                    "large high-risk file changed above threshold: "
                    f"{item.path} ({line_count} lines, "
                    f"{item.changed_lines} changed lines)"
                ),
                affected_paths=(normalized,),
            )
        )
    return findings


def _detect_seam_candidates(
    changed_files: list[ChangedFile], policy: dict[str, Any]
) -> list[str]:
    seam_policy = policy.get("accepted_seam_markers", {})
    fragments = [item.lower() for item in seam_policy.get("file_name_fragments", [])]
    suffixes = {
        item.lower()
        for item in seam_policy.get("code_suffixes", [".py"])
    }

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
    return sorted(set(candidates))


def _python_imports_candidate(content: str, candidate_path: str) -> bool:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False

    candidate = PurePosixPath(candidate_path)
    stem = candidate.stem
    dotted_path = ".".join(candidate.with_suffix("").parts)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (
                    alias.name == stem
                    or alias.name == dotted_path
                    or alias.name.endswith(f".{stem}")
                ):
                    return True
        if isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if module_name == stem or module_name.endswith(f".{stem}"):
                return True
            if any(alias.name == stem for alias in node.names):
                return True
    return False


def _script_imports_candidate(content: str, candidate_path: str) -> bool:
    stem = re.escape(PurePosixPath(candidate_path).stem)
    module_tail = rf"[^\"'\n]*[/\\.]?{stem}(?:\.[a-z0-9]+)?"
    patterns = (
        rf"^\s*import\s+(?:[^;\n]*?\s+from\s+)?[\"']{module_tail}[\"']",
        rf"^\s*export\s+[^;\n]*?\s+from\s+[\"']{module_tail}[\"']",
        rf"^\s*(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*"
        rf"require\s*\(\s*[\"']{module_tail}[\"']\s*\)",
        rf"^\s*(?:(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*)?"
        rf"(?:await\s+)?import\s*\(\s*[\"']{module_tail}[\"']\s*\)",
    )
    return any(
        re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
        for pattern in patterns
    )


def _imports_candidate(
    *,
    repo_root: Path,
    caller_path: str,
    candidate_path: str,
) -> bool:
    normalized_caller = _normalize_path(caller_path)
    normalized_candidate = _normalize_path(candidate_path)
    if normalized_caller == normalized_candidate:
        return False

    caller = repo_root / normalized_caller
    if not caller.exists() or not caller.is_file():
        return False
    content = _read_text(caller)
    suffix = caller.suffix.lower()
    if suffix == ".py":
        return _python_imports_candidate(content, normalized_candidate)
    if suffix in SCRIPT_SUFFIXES:
        return _script_imports_candidate(content, normalized_candidate)
    return False


def _related_seam_evidence(
    *,
    repo_root: Path,
    finding: RiskFinding,
    seam_candidates: list[str],
) -> tuple[str, str] | None:
    for candidate in seam_candidates:
        for affected_path in finding.affected_paths:
            if _imports_candidate(
                repo_root=repo_root,
                caller_path=affected_path,
                candidate_path=candidate,
            ):
                return candidate, affected_path
    return None


def _field_value(body: str, field: str) -> str | None:
    pattern = re.compile(
        rf"^\s*[-*]?\s*{re.escape(field)}\s*:\s*(.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(body)
    if not match:
        return None
    return match.group(1).strip()


def _validate_exception_body(
    policy: dict[str, Any],
    body: str,
    risky_paths: set[str],
) -> tuple[bool, list[str]]:
    markers = policy.get("exception_markers", {})
    claim_markers = [item.lower() for item in markers.get("claim_markers", [])]
    required_fields = markers.get("required_fields", [])
    minimum_chars = int(markers.get("minimum_explanation_characters", 20))
    rejected_values = PLACEHOLDER_VALUES | {
        str(item).strip().lower()
        for item in markers.get("rejected_values", [])
    }

    lowered = body.lower()
    claim_found = any(
        f"[x] {marker}" in lowered
        or f"{marker}: yes" in lowered
        or f"{marker}: true" in lowered
        for marker in claim_markers
    )

    errors: list[str] = []
    if not claim_found:
        errors.append("missing checked leaf-only exception claim")

    field_values: dict[str, str] = {}
    for field in required_fields:
        value = _field_value(body, field)
        if value is None:
            errors.append(f"missing exception field: {field}")
            continue
        field_values[field.lower()] = value

    changed_files_value = field_values.get("changed files")
    if changed_files_value is not None:
        normalized_value = _normalize_path(changed_files_value)
        for risky_path in sorted(risky_paths):
            if risky_path not in normalized_value:
                errors.append(
                    f"exception Changed files missing risky path: {risky_path}"
                )

    for field in required_fields:
        if field.lower() == "changed files":
            continue
        value = field_values.get(field.lower())
        if value is None:
            continue
        if value.lower() in rejected_values:
            errors.append(f"placeholder exception field: {field}")
        elif len(value) < minimum_chars:
            errors.append(
                f"exception field too short: {field} "
                f"({len(value)}<{minimum_chars})"
            )

    return not errors, errors


def evaluate_modular_entry_guard(
    *,
    repo_root: Path,
    policy: dict[str, Any],
    changed_files: list[ChangedFile],
    event_name: str,
    pr_body: str,
) -> tuple[bool, list[str]]:
    line_threshold = int(policy.get("large_file_line_threshold", 500))
    changed_lines_threshold = int(
        policy.get("large_file_changed_lines_threshold", 20)
    )
    findings = [
        *_collect_cross_surface_findings(changed_files, policy),
        *_collect_protected_findings(
            changed_files,
            policy,
            changed_lines_threshold,
        ),
        *_collect_large_file_findings(
            repo_root,
            changed_files,
            policy,
            line_threshold,
            changed_lines_threshold,
        ),
    ]
    if not findings:
        return True, ["no risky changes detected"]

    messages = [finding.message for finding in findings]
    seam_candidates = _detect_seam_candidates(changed_files, policy)
    related_evidence: list[tuple[str, str, str]] = []
    missing_findings: list[RiskFinding] = []
    for finding in findings:
        evidence = _related_seam_evidence(
            repo_root=repo_root,
            finding=finding,
            seam_candidates=seam_candidates,
        )
        if evidence is None:
            missing_findings.append(finding)
            continue
        candidate, caller = evidence
        related_evidence.append((finding.kind, candidate, caller))

    if not missing_findings:
        used_candidates = sorted(
            {candidate for _, candidate, _ in related_evidence}
        )
        messages.append(
            f"seam evidence detected via {', '.join(used_candidates)}"
        )
        messages.extend(
            f"related seam handoff: {kind} {caller} -> {candidate}"
            for kind, candidate, caller in related_evidence
        )
        return True, messages

    for finding in missing_findings:
        messages.append(
            f"missing related seam handoff for: {finding.message}"
        )
    if seam_candidates:
        messages.append(
            "unrelated seam candidates ignored: "
            f"{', '.join(seam_candidates)}"
        )

    event_rules = policy.get("event_rules", {}).get(event_name, {})
    if event_rules.get("allow_leaf_only_exception"):
        risky_paths = {
            path
            for finding in findings
            for path in finding.affected_paths
        }
        is_valid_exception, exception_errors = _validate_exception_body(
            policy,
            pr_body,
            risky_paths,
        )
        if is_valid_exception:
            return True, [*messages, "valid leaf-only exception provided"]
        messages.extend(exception_errors)
    else:
        messages.append("leaf-only exceptions are not allowed for this event")

    messages.append("missing modular entrypoint evidence")
    return False, messages
