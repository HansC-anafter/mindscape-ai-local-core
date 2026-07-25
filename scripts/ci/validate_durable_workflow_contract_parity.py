#!/usr/bin/env python3
"""Validate the checked-in Local durable contract mirror byte for byte."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_RELATIVE_ROOT = Path(
    "backend/app/services/workflow/durable_state/contracts/v1"
)
CANONICAL_RELATIVE_ROOT = Path(
    "contracts/durable_product_semantic_workflow/v1"
)
DEFAULT_CONTRACT_SOURCE = Path(
    ".contract-sources/mindscape-ai-cloud"
)


def validate_parity(
    *,
    local_root: Path,
    canonical_root: Path,
) -> list[str]:
    errors: list[str] = []
    canonical_manifest_path = canonical_root / "release_manifest.json"
    local_manifest_path = local_root / "release_manifest.json"
    if not canonical_manifest_path.exists():
        return [f"canonical release manifest is missing: {canonical_manifest_path}"]
    if not local_manifest_path.exists():
        return [f"local release manifest is missing: {local_manifest_path}"]
    if canonical_manifest_path.read_bytes() != local_manifest_path.read_bytes():
        errors.append("release_manifest.json parity drift")
    manifest = json.loads(canonical_manifest_path.read_text(encoding="utf-8"))
    source_manifest_path = local_root / "source_manifest.json"
    if not source_manifest_path.exists():
        errors.append(f"local source manifest is missing: {source_manifest_path}")
    else:
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        release_bytes = canonical_manifest_path.read_bytes()
        if source_manifest.get("release_manifest_file_sha256") != hashlib.sha256(
            release_bytes
        ).hexdigest():
            errors.append("source manifest release file hash mismatch")
        if (
            source_manifest.get("release_manifest_content_sha256")
            != manifest.get("manifest_sha256")
        ):
            errors.append("source manifest canonical content hash mismatch")
        for key in ("cloud_psc_id", "local_core_psc_id", "source_revision_binding"):
            if source_manifest.get(key) != manifest.get(key):
                errors.append(f"source manifest {key} mismatch")
        canonical_repo = canonical_root.parents[2]
        if (canonical_repo / ".git").exists():
            source_commit = str(source_manifest.get("cloud_commit_sha") or "")
            commit = subprocess.run(
                ["git", "-C", str(canonical_repo), "rev-parse", f"{source_commit}^{{commit}}"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
            tree = subprocess.run(
                ["git", "-C", str(canonical_repo), "rev-parse", f"{source_commit}^{{tree}}"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
            if source_commit != commit:
                errors.append("source manifest Cloud commit is not canonical")
            if source_manifest.get("cloud_tree_sha") != tree:
                errors.append("source manifest Cloud tree mismatch")
    for relative, receipt in manifest.get("schemas", {}).items():
        canonical = canonical_root / relative
        local = local_root / relative
        if not canonical.exists() or not local.exists():
            errors.append(f"missing mirrored schema: {relative}")
            continue
        canonical_bytes = canonical.read_bytes()
        if canonical_bytes != local.read_bytes():
            errors.append(f"byte parity drift: {relative}")
            continue
        digest = hashlib.sha256(canonical_bytes).hexdigest()
        if digest != receipt.get("sha256") or len(canonical_bytes) != receipt.get("bytes"):
            errors.append(f"manifest receipt mismatch: {relative}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    parser.add_argument("--contract-source")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    contract_source = (
        Path(args.contract_source).resolve()
        if args.contract_source
        else (repo_root / DEFAULT_CONTRACT_SOURCE).resolve()
    )
    errors = validate_parity(
        local_root=repo_root / LOCAL_RELATIVE_ROOT,
        canonical_root=contract_source / CANONICAL_RELATIVE_ROOT,
    )
    if errors:
        print("Durable workflow contract parity failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Durable workflow contract parity passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
