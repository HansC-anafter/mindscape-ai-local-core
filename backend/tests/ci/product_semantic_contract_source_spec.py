import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPO_ROOT / "scripts" / "ci" / "validate_product_semantics.py"
SURFACE_ID = "psc.test.contract-source.v1"
CONTRACT_DOC = (
    "mindscape-ai-cloud/docs/internal/local-core/product-semantics/"
    "test-contract-source-2026-06-21.zh-TW.md"
)
CONTRACT_INDEX = (
    "docs/internal/local-core/product-semantics/"
    "product-semantic-contract-index-2026-06-21.zh-TW.md"
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _init_registry(repo: Path) -> Path:
    registry_path = repo / "ci" / "product_semantic_surfaces.yaml"
    _write(
        registry_path,
        f"""version: 1
registry_id: test.product-semantic-surfaces
updated_at: "2026-06-21"
owner_review_handle: "@team-leads"

declaration:
  allowed_values:
    - none
    - approved
  required_marker: product-semantic-change
  approval_fields:
    - semantic-decision-record
    - breaking-product-semantics-approved-by

surfaces:
  - id: {SURFACE_ID}
    tier: P0
    owner: "@team-leads"
    contract_doc: {CONTRACT_DOC}
    requires_product_semantic_declaration: true
    semantics:
      - Explicit contract source roots must resolve cloud-owned contract docs.
    path_globs:
      - backend/app/example_surface.py
""",
    )
    return registry_path


def _init_contract_root(tmp_path: Path) -> Path:
    contract_root = tmp_path / "cloud-contract-source"
    _write(contract_root / CONTRACT_INDEX, f"# Contract Index\n\n- `{SURFACE_ID}`\n")
    _write(
        contract_root
        / "docs/internal/local-core/product-semantics/test-contract-source-2026-06-21.zh-TW.md",
        f"# Test Contract\n\nSurface: `{SURFACE_ID}`\n",
    )
    return contract_root


def _run_registry_only(
    repo: Path,
    registry_path: Path,
    contract_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(VALIDATOR),
        "--repo-root",
        str(repo),
        "--registry",
        str(registry_path),
        "--event-name",
        "push",
        "--base-sha",
        "1" * 40,
        "--head-sha",
        "1" * 40,
        "--validate-registry-only",
    ]
    if contract_root is not None:
        command.extend(["--contract-root", str(contract_root)])
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_registry_only_accepts_explicit_cloud_contract_root(tmp_path: Path) -> None:
    repo = tmp_path / "local-core"
    registry_path = _init_registry(repo)
    contract_root = _init_contract_root(tmp_path)

    result = _run_registry_only(repo, registry_path, contract_root)

    assert result.returncode == 0, result.stderr
    assert "Product semantic registry is valid" in result.stdout


def test_registry_only_rejects_missing_explicit_and_sibling_contract_source(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "local-core"
    registry_path = _init_registry(repo)
    _init_contract_root(tmp_path)

    result = _run_registry_only(repo, registry_path)

    assert result.returncode == 1
    assert SURFACE_ID in result.stderr
    assert "Product semantic contract index is missing" in result.stderr
    assert "contract_doc is missing" in result.stderr
