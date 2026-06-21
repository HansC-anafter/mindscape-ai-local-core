import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPO_ROOT / "scripts" / "ci" / "validate_product_semantics.py"

REGISTRY = """
version: 1
registry_id: test.local-core-product-semantics
declaration:
  allowed_values:
    - none
    - approved
  required_marker: product-semantic-change
  approval_fields:
    - semantic-decision-record
    - breaking-product-semantics-approved-by
surfaces:
  - id: psc.test.queue-snapshot.v1
    tier: P0
    owner: "@team-leads"
    contract_doc: docs/contracts/queue-snapshot.md
    requires_product_semantic_declaration: true
    path_globs:
      - backend/app/services/host_resources/**
    content_assertions:
      - path: backend/app/services/host_resources/queue_utilization_snapshot_store.py
        forbidden_text:
          - token: latest_batch
            message: latest_batch is not allowed
        required_text:
          - token: DISTINCT ON (queue_shard)
            message: per-shard row selection is required
          - token: captured_at_by_queue_shard
            message: per-shard freshness is required
      - path: backend/app/services/host_resources/queue_utilization_live.py
        required_text:
          - token: visible_lane_identity
            message: route-lane identity is required
          - token: read_route_identity_projections_func
            message: route projection reader is required
          - token: lanes = visible_lanes(task_ids=task_ids, projections=projections)
            message: visible_lanes must come from route projections
  - id: psc.test.capability-install.v1
    tier: P0
    owner: "@team-leads"
    contract_doc: docs/contracts/capability-install.md
    requires_product_semantic_declaration: true
    path_globs:
      - backend/app/routes/core/capability_install_core/**
    content_assertions:
      - path: backend/app/routes/core/capability_install_core/routes.py
        required_text:
          - token: _require_control_plane_install("install-from-file")
            message: file install must remain control-plane only
          - token: create_file_upload_job
            message: file install must create a durable install job
          - token: accepted
            message: accepted-only response semantics are required
          - token: install_id
            message: durable install id is required
          - token: status_url
            message: job polling URL is required
  - id: psc.test.semantic-governance.v1
    tier: P0
    owner: "@team-leads"
    contract_doc: docs/contracts/semantic-governance.md
    requires_product_semantic_declaration: true
    path_globs:
      - .github/workflows/architecture-guardrails.yml
    content_assertions:
      - path: .github/workflows/architecture-guardrails.yml
        required_text:
          - token: device-node/**
            message: registered device-node semantic surfaces must trigger guardrails
  - id: psc.test.capture-relay.v1
    tier: P1
    owner: "@team-leads"
    contract_doc: docs/contracts/capture-relay.md
    requires_product_semantic_declaration: true
    path_globs:
      - device-node/src/**
"""

CONTRACT_INDEX = """
# Product Semantic Contract Index

### `psc.test.queue-snapshot.v1`
### `psc.test.capability-install.v1`
### `psc.test.semantic-governance.v1`
### `psc.test.capture-relay.v1`
"""

PREFLIGHT_NONE = """
Product Semantic Panoramic Preflight:
scope-class: normal-repair
protected-behavior: Registered Local Core product semantics remain stable.
source-of-truth: ci/product_semantic_surfaces.yaml and Local Core contract docs.
registry-scan: test registry checked for psc.test.* surfaces.
impacted-psc: psc.test.capability-install.v1
contract-index-read: docs/contracts/semantic-governance.md
adjacent-surface-scan: backend routes, services, workflow, and device-node surfaces checked.
semantic-decision: preserve
verification-mapping: focused validator regression tests.

product-semantic-change: none
"""

PREFLIGHT_APPROVED = """
Product Semantic Panoramic Preflight:
scope-class: boundary-crossing-repair
protected-behavior: Registered Local Core product semantics are intentionally changed.
source-of-truth: ci/product_semantic_surfaces.yaml and Local Core contract docs.
registry-scan: test registry checked for psc.test.* surfaces.
impacted-psc: psc.test.capability-install.v1
contract-index-read: docs/contracts/semantic-governance.md
adjacent-surface-scan: backend routes, services, workflow, and device-node surfaces checked.
semantic-decision: approved-change
verification-mapping: focused validator regression tests.

product-semantic-change: approved
"""

SNAPSHOT_STORE = '''
def latest_snapshot():
    query = """SELECT DISTINCT ON (queue_shard) captured_at, queue_shard FROM snapshots"""
    return {"captured_at_by_queue_shard": {}, "query": query}
'''

LIVE_QUEUE = '''
def visible_lane_identity(projection):
    return "route_lane", projection.get("lane_id")

async def build(read_route_identity_projections_func):
    projections = await read_route_identity_projections_func(None, [])
    lanes = visible_lanes(task_ids=task_ids, projections=projections)
    resource_lanes = {"default": [{"lane_key": "runner_profile:default"}]}
    return {"visible_lanes": lanes, "resource_lanes": resource_lanes}
'''


def preflight_none(*surface_ids: str) -> str:
    return PREFLIGHT_NONE.replace(
        "impacted-psc: psc.test.capability-install.v1",
        f"impacted-psc: {', '.join(surface_ids)}",
    )


def preflight_approved(*surface_ids: str) -> str:
    return PREFLIGHT_APPROVED.replace(
        "impacted-psc: psc.test.capability-install.v1",
        f"impacted-psc: {', '.join(surface_ids)}",
    )


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def init_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "checkout", "-B", "master")
    git(repo, "config", "user.email", "guardrail@example.com")
    git(repo, "config", "user.name", "Guardrail Test")
    write(repo / "ci/product_semantic_surfaces.yaml", REGISTRY)
    write(
        repo
        / "docs/internal/local-core/product-semantics/product-semantic-contract-index-2026-06-21.zh-TW.md",
        CONTRACT_INDEX,
    )
    write(repo / "docs/contracts/queue-snapshot.md", "psc.test.queue-snapshot.v1\n")
    write(repo / "docs/contracts/capability-install.md", "psc.test.capability-install.v1\n")
    write(repo / "docs/contracts/semantic-governance.md", "psc.test.semantic-governance.v1\n")
    write(repo / "docs/contracts/capture-relay.md", "psc.test.capture-relay.v1\n")
    write(
        repo / "backend/app/services/host_resources/queue_utilization_snapshot_store.py",
        SNAPSHOT_STORE,
    )
    write(repo / "backend/app/services/host_resources/queue_utilization_live.py", LIVE_QUEUE)
    write(
        repo / "backend/app/routes/core/capability_install_core/routes.py",
        '''
def install_from_file():
    _require_control_plane_install("install-from-file")
    job = service.create_file_upload_job()
    return {
        "accepted": True,
        "install_id": job["install_id"],
        "status_url": job["status_url"],
    }
''',
    )
    write(
        repo / ".github/workflows/architecture-guardrails.yml",
        """
on:
  pull_request:
    paths:
      - 'backend/app/**'
      - 'backend/tests/**'
      - 'device-node/**'
      - '.github/workflows/**'
  push:
    paths:
      - 'backend/app/**'
      - 'backend/tests/**'
      - 'device-node/**'
      - '.github/workflows/**'
""",
    )
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    return repo, git(repo, "rev-parse", "HEAD")


def run_validator(
    repo: Path,
    *,
    base_sha: str,
    head_sha: str,
    event_name: str = "pull_request",
    pr_body: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(VALIDATOR),
        "--repo-root",
        str(repo),
        "--registry",
        str(repo / "ci/product_semantic_surfaces.yaml"),
        "--event-name",
        event_name,
        "--base-sha",
        base_sha,
        "--head-sha",
        head_sha,
    ]
    if pr_body is not None:
        body_path = repo / "pr_body.md"
        body_path.write_text(pr_body, encoding="utf-8")
        command.extend(["--pr-body-file", str(body_path)])
    return subprocess.run(command, check=False, capture_output=True, text=True)


def run_registry_only(repo: Path, *, base_sha: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--repo-root",
            str(repo),
            "--registry",
            str(repo / "ci/product_semantic_surfaces.yaml"),
            "--event-name",
            "push",
            "--base-sha",
            base_sha,
            "--head-sha",
            base_sha,
            "--validate-registry-only",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
