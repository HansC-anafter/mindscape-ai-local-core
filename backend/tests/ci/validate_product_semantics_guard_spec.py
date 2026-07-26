import sys
from pathlib import Path

import yaml

from product_semantic_validator_fixtures import (
    LIVE_QUEUE,
    git as _git,
    init_repo as _init_repo,
    preflight_approved as _preflight_approved,
    preflight_none as _preflight_none,
    run_registry_only as _run_registry_only,
    run_validator as _run_validator,
    write as _write,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_registry_declares_workbench_ui_locale_authority_surface() -> None:
    registry = yaml.safe_load(
        (REPO_ROOT / "ci/product_semantic_surfaces.yaml").read_text(encoding="utf-8")
    )
    surfaces = {
        surface["id"]: surface
        for surface in registry["surfaces"]
    }
    surface = surfaces["psc.local-core.workbench-ui-locale-authority.v1"]

    assert surface["tier"] == "P0"
    assert surface["requires_product_semantic_declaration"] is True
    assert surface["contract_doc"].endswith(
        "workbench-unified-ui-locale-and-pack-localization-contract-2026-07-27.zh-TW.md"
    )
    assert "backend/features/mindscape/routes_profiles_intents.py" in surface["path_globs"]
    assert "backend/app/routes/core/user_profiles.py" not in surface["path_globs"]


def test_registry_only_validation_accepts_valid_registry(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    result = _run_registry_only(repo, base_sha=base_sha)

    assert result.returncode == 0
    assert "Product semantic registry is valid" in result.stdout


def test_registry_validation_rejects_missing_contract_doc(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    (repo / "docs/contracts/capability-install.md").unlink()

    result = _run_registry_only(repo, base_sha=base_sha)

    assert result.returncode == 1
    assert "contract_doc is missing" in result.stderr
    assert "psc.test.capability-install.v1" in result.stderr


def test_registry_validation_rejects_contract_doc_without_surface_id(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(repo / "docs/contracts/capability-install.md", "wrong surface\n")

    result = _run_registry_only(repo, base_sha=base_sha)

    assert result.returncode == 1
    assert "contract_doc must name the registered surface id" in result.stderr
    assert "psc.test.capability-install.v1" in result.stderr


def test_pr_touching_registered_local_core_surface_requires_declaration(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(repo / "backend/app/routes/core/capability_install_core/routes.py", "ROUTE = 'changed'\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "change capability install")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(repo, base_sha=base_sha, head_sha=head_sha, pr_body="")

    assert result.returncode == 1
    assert "product-semantic-change: none" in result.stderr
    assert "psc.test.capability-install.v1:backend/app/routes/core/capability_install_core/routes.py" in result.stderr


def test_resource_lane_tokens_do_not_fail_when_visible_lanes_are_route_derived(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / "backend/app/services/host_resources/queue_utilization_live.py",
        LIVE_QUEUE + "\\nRESOURCE_LANE = 'host_lane:gpu'\\n",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "keep resource lanes separate")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(
        repo,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_body=_preflight_none("psc.test.queue-snapshot.v1"),
    )

    assert result.returncode == 0
    assert "Product semantic guardrail passed" in result.stdout


def test_snapshot_reader_rejects_global_latest_batch(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / "backend/app/services/host_resources/queue_utilization_snapshot_store.py",
        "latest_batch = 'bad'\n",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "break snapshot reader")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(
        repo,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_body=_preflight_none("psc.test.queue-snapshot.v1"),
    )

    assert result.returncode == 1
    assert "latest_batch is not allowed" in result.stderr
    assert "per-shard row selection is required" in result.stderr
    assert "per-shard freshness is required" in result.stderr


def test_approved_declaration_requires_decision_record_and_approver(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(repo / "backend/app/routes/core/capability_install_core/routes.py", "ROUTE = 'approved'\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "approved semantic change")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(
        repo,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_body=_preflight_approved("psc.test.capability-install.v1"),
    )

    assert result.returncode == 1
    assert "semantic-decision-record" in result.stderr
    assert "breaking-product-semantics-approved-by" in result.stderr


def test_pr_touching_registered_surface_requires_matching_impacted_psc(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(repo / "backend/app/routes/core/capability_install_core/routes.py", "ROUTE = 'changed'\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "change capability install")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(
        repo,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_body=_preflight_none("psc.test.queue-snapshot.v1"),
    )

    assert result.returncode == 1
    assert "impacted-psc" in result.stderr
    assert "expected: psc.test.capability-install.v1" in result.stderr
    assert "declared: psc.test.queue-snapshot.v1" in result.stderr


def test_pr_touching_registered_surface_requires_panoramic_preflight_fields(
    tmp_path: Path,
) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(repo / "backend/app/routes/core/capability_install_core/routes.py", "ROUTE = 'changed'\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "change capability install")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(
        repo,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_body="product-semantic-change: none\n",
    )

    assert result.returncode == 1
    assert "Product Semantic Panoramic Preflight" in result.stderr
    assert "`scope-class:`" in result.stderr
    assert "`semantic-decision:`" in result.stderr


def test_capability_install_assertion_rejects_synchronous_install_response(tmp_path: Path) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / "backend/app/routes/core/capability_install_core/routes.py",
        "def install_from_file():\n    return {'success': True}\n",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "weaken install intake")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(
        repo,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_body=_preflight_none("psc.test.capability-install.v1"),
    )

    assert result.returncode == 1
    assert "file install must remain control-plane only" in result.stderr
    assert "file install must create a durable install job" in result.stderr
    assert "job polling URL is required" in result.stderr


def test_semantic_governance_assertion_rejects_missing_device_node_trigger(
    tmp_path: Path,
) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / ".github/workflows/architecture-guardrails.yml",
        """
on:
  pull_request:
    paths:
      - 'backend/app/**'
""",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "weaken device node guardrail trigger")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(
        repo,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_body=_preflight_none("psc.test.semantic-governance.v1"),
    )

    assert result.returncode == 1
    assert "registered device-node semantic surfaces must trigger guardrails" in result.stderr


def test_workflow_coverage_rejects_registered_device_node_surface_without_trigger(
    tmp_path: Path,
) -> None:
    repo, base_sha = _init_repo(tmp_path)
    _write(
        repo / ".github/workflows/architecture-guardrails.yml",
        """
on:
  pull_request:
    paths:
      - 'backend/app/**'
      - 'backend/tests/**'
      - '.github/workflows/**'
  push:
    paths:
      - 'backend/app/**'
      - 'backend/tests/**'
      - '.github/workflows/**'
""",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "remove device node workflow coverage")
    head_sha = _git(repo, "rev-parse", "HEAD")

    result = _run_validator(
        repo,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_body=_preflight_none("psc.test.semantic-governance.v1"),
    )

    assert result.returncode == 1
    assert "paths do not cover registry path_glob `device-node/src/**`" in result.stderr


def test_normalize_path_preserves_dot_directories() -> None:
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from scripts.ci import validate_product_semantics as module
    finally:
        sys.path.pop(0)

    assert module._normalize_path("./.github/pull_request_template.md") == (
        ".github/pull_request_template.md"
    )
    assert module._normalize_path(".github/workflows/architecture-guardrails.yml") == (
        ".github/workflows/architecture-guardrails.yml"
    )


def test_remote_workbench_registry_matches_literal_dynamic_route_directories() -> None:
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from scripts.ci import validate_product_semantics as module
    finally:
        sys.path.pop(0)

    registry = module._load_registry(REPO_ROOT / "ci/product_semantic_surfaces.yaml")
    surface_id = "psc.local-core.remote-workbench-identity-workspace-enforcement.v1"
    paths = {
        "web-console/src/app/workspaces/[workspaceId]/page.tsx",
        "web-console/src/app/workspaces/[workspaceId]/RemoteWorkspaceLanding.tsx",
        "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/WorkspaceSurfaceShell.tsx",
        "web-console/src/app/workspaces/[workspaceId]/capabilities/[capabilityCode]/CapabilityLoadedComponents.tsx",
    }

    hits = set(
        module._registered_surface_hits(registry=registry, changed_files=paths)
    )

    assert {(surface_id, path) for path in paths}.issubset(hits)
