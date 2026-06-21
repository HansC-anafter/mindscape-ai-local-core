import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPO_ROOT / "scripts" / "ci" / "validate_product_semantic_helper_parity.py"
HELPER_SOURCE = '''"""Shared traceability checks for product semantic validators."""

from __future__ import annotations

VALUE = "same"
'''


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--repo-root",
            str(repo),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _init_repo(tmp_path: Path, *, local_source: str = HELPER_SOURCE) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "scripts/ci/product_semantic_traceability.py", local_source)
    _write(
        repo
        / ".contract-sources/mindscape-ai-cloud/scripts/product_semantic_traceability.py",
        HELPER_SOURCE,
    )
    return repo


def test_helper_parity_accepts_identical_sources(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    result = _run(repo)

    assert result.returncode == 0, result.stderr
    assert "Product semantic traceability helper parity passed" in result.stdout


def test_helper_parity_rejects_local_drift(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, local_source=HELPER_SOURCE.replace('"same"', '"drift"'))

    result = _run(repo)

    assert result.returncode == 1
    assert "Product semantic traceability helper parity failed" in result.stderr
    assert "parity drift detected" in result.stderr
    assert "---" in result.stderr
    assert "+++" in result.stderr
    assert '-VALUE = "same"' in result.stderr
    assert '+VALUE = "drift"' in result.stderr
