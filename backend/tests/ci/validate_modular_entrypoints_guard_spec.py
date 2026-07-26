import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPO_ROOT / "scripts" / "ci" / "validate_modular_entrypoints.py"

POLICY = """
large_file_line_threshold: 500
large_file_changed_lines_threshold: 20
high_risk_paths:
  - backend/app/services/**
multi_surface_groups:
  - name: temp-runtime
    surfaces:
      services:
        - backend/app/services/**
      routes:
        - backend/app/routes/core/**
protected_monoliths:
  - path: backend/app/services/giant_service.py
    diff_budget: 5
accepted_seam_markers:
  file_name_fragments:
    - facade
    - adapter
    - shim
    - dispatcher
    - compat
    - wrapper
    - bridge
  code_suffixes:
    - .py
event_rules:
  pull_request:
    allow_leaf_only_exception: true
    require_pr_body_for_exception: true
  push:
    allow_leaf_only_exception: false
    require_pr_body_for_exception: false
exception_markers:
  claim_markers:
    - Leaf-only exception claimed
  minimum_explanation_characters: 20
  rejected_values:
    - "-"
    - n/a
    - none
    - todo
    - tbd
  required_fields:
    - Changed files
    - Why leaf-only
    - Why no new boundary
    - Why future refactor cost does not increase
"""


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _load_validator_module():
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from scripts.ci import validate_modular_entrypoints as module
    finally:
        sys.path.pop(0)
    return module


def _build_large_service(module_name: str = "giant_service_facade") -> str:
    lines = ["from __future__ import annotations", "", f"import {module_name}", "", ""]
    lines.extend(f"LINE_{index} = {index}" for index in range(560))
    lines.append("")
    lines.append("def run() -> str:")
    lines.append(f"    return {module_name}.execute()")
    lines.append("")
    return "\n".join(lines)


def _mutate_large_service(module_name: str, *, bump: int) -> str:
    content = _build_large_service(module_name)
    for index in range(8):
        content = content.replace(
            f"LINE_{index} = {index}",
            f"LINE_{index} = {index + bump}",
        )
    return content


def _init_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-B", "master")
    _git(repo, "config", "user.email", "guardrail@example.com")
    _git(repo, "config", "user.name", "Guardrail Test")
    _write(repo / "policy.yaml", POLICY)
    _write(repo / "backend/app/services/giant_service.py", _build_large_service("legacy_adapter"))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _run_validator(
    repo: Path,
    *,
    base_sha: str,
    head_sha: str,
    event_name: str = "pull_request",
    pr_body: str | None = None,
):
    command = [
        sys.executable,
        str(VALIDATOR),
        "--repo-root",
        str(repo),
        "--event-name",
        event_name,
        "--base-sha",
        base_sha,
        "--head-sha",
        head_sha,
        "--policy",
        str(repo / "policy.yaml"),
    ]
    if pr_body is not None:
        body_path = repo / "pr_body.md"
        body_path.write_text(pr_body, encoding="utf-8")
        command.extend(["--pr-body-file", str(body_path)])
    return subprocess.run(command, check=False, capture_output=True, text=True)


def test_validator_rejects_protected_monolith_without_seam(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / "backend/app/services/giant_service.py",
        _mutate_large_service("legacy_adapter", bump=900),
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "change giant service directly")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(repo, base_sha=base_sha, head_sha=head_sha, pr_body="")

    assert result.returncode == 1
    assert "protected monolith exceeded diff budget" in result.stdout
    assert "missing modular entrypoint evidence" in result.stdout


def test_validator_accepts_seam_extraction_for_protected_monolith(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / "backend/app/services/giant_service_facade.py",
        "def execute() -> str:\n    return 'ok'\n",
    )
    _write(
        repo / "backend/app/services/giant_service.py",
        _mutate_large_service("giant_service_facade", bump=700),
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "extract giant service facade")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(repo, base_sha=base_sha, head_sha=head_sha, pr_body="")

    assert result.returncode == 0
    assert "seam evidence detected via backend/app/services/giant_service_facade.py" in result.stdout


def test_validator_rejects_unrelated_facade_for_protected_monolith(
    tmp_path: Path,
) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / "backend/app/services/unrelated/noop_facade.py",
        "def execute() -> str:\n    return 'unrelated'\n",
    )
    _write(
        repo / "backend/app/services/giant_service.py",
        _mutate_large_service("legacy_adapter", bump=800),
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add unrelated facade")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(repo, base_sha=base_sha, head_sha=head_sha, pr_body="")

    assert result.returncode == 1
    assert "unrelated seam candidates ignored" in result.stdout
    assert "missing related seam handoff" in result.stdout


@pytest.mark.parametrize(
    ("line_count", "expected_valid"),
    [(499, True), (500, False), (501, False)],
)
def test_large_file_threshold_is_inclusive_at_500(
    tmp_path: Path,
    line_count: int,
    expected_valid: bool,
) -> None:
    module = _load_validator_module()
    relative_path = "backend/app/services/sized_service.py"
    _write(
        tmp_path / relative_path,
        "\n".join(f"LINE_{index} = {index}" for index in range(line_count)),
    )
    changed = module.ChangedFile(
        path=relative_path,
        status="M",
        additions=21,
        deletions=0,
    )

    is_valid, _ = module.evaluate_modular_entry_guard(
        repo_root=tmp_path,
        policy=yaml.safe_load(POLICY),
        changed_files=[changed],
        event_name="pull_request",
        pr_body="",
    )

    assert is_valid is expected_valid


@pytest.mark.parametrize(
    ("changed_lines", "expected_valid"),
    [(20, True), (21, False)],
)
def test_changed_line_threshold_triggers_above_20(
    tmp_path: Path,
    changed_lines: int,
    expected_valid: bool,
) -> None:
    module = _load_validator_module()
    relative_path = "backend/app/services/sized_service.py"
    _write(
        tmp_path / relative_path,
        "\n".join(f"LINE_{index} = {index}" for index in range(500)),
    )
    changed = module.ChangedFile(
        path=relative_path,
        status="M",
        additions=changed_lines,
        deletions=0,
    )

    is_valid, _ = module.evaluate_modular_entry_guard(
        repo_root=tmp_path,
        policy=yaml.safe_load(POLICY),
        changed_files=[changed],
        event_name="pull_request",
        pr_body="",
    )

    assert is_valid is expected_valid


def test_validator_accepts_leaf_only_exception_on_pull_request(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / "backend/app/services/giant_service.py",
        _mutate_large_service("legacy_adapter", bump=500),
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "leaf only change")
    head_sha = _git(repo, "rev-parse", "HEAD")

    pr_body = """
- [x] Leaf-only exception claimed

Changed files: backend/app/services/giant_service.py
Why leaf-only: updates a local constant without opening a new boundary.
Why no new boundary: request flow and module ownership stay unchanged.
Why future refactor cost does not increase: no new dependency edge is introduced.
"""

    result = _run_validator(repo, base_sha=base_sha, head_sha=head_sha, pr_body=pr_body)

    assert result.returncode == 0
    assert "valid leaf-only exception provided" in result.stdout


def test_leaf_exception_must_name_every_cross_surface_path(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / "backend/app/services/secondary_service.py",
        "def run() -> str:\n    return 'service'\n",
    )
    _write(
        repo / "backend/app/routes/core/demo.py",
        "def route() -> str:\n    return 'route'\n",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "cross surface leaf claim")
    head_sha = _git(repo, "rev-parse", "HEAD")
    pr_body = """
- [x] Leaf-only exception claimed

Changed files: backend/app/services/secondary_service.py
Why leaf-only: only local return values change in the existing functions.
Why no new boundary: ownership and the canonical request path remain unchanged.
Why future refactor cost does not increase: no dependency or responsibility is added.
"""

    result = _run_validator(
        repo,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_body=pr_body,
    )

    assert result.returncode == 1
    assert (
        "exception Changed files missing risky path: "
        "backend/app/routes/core/demo.py"
    ) in result.stdout


def test_leaf_exception_rejects_placeholder_explanation(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / "backend/app/services/giant_service.py",
        _mutate_large_service("legacy_adapter", bump=600),
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "placeholder leaf claim")
    head_sha = _git(repo, "rev-parse", "HEAD")
    pr_body = """
- [x] Leaf-only exception claimed

Changed files: backend/app/services/giant_service.py
Why leaf-only: N/A
Why no new boundary: ownership and the canonical request path remain unchanged.
Why future refactor cost does not increase: no dependency or responsibility is added.
"""

    result = _run_validator(
        repo,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_body=pr_body,
    )

    assert result.returncode == 1
    assert "placeholder exception field: Why leaf-only" in result.stdout
