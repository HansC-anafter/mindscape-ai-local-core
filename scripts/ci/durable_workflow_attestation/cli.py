"""Command-line composition for CI-only attestation drafts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import build_attestation_draft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud-repo", required=True)
    parser.add_argument("--local-repo", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    draft = build_attestation_draft(
        cloud_repo=Path(args.cloud_repo),
        local_repo=Path(args.local_repo),
        evidence=evidence,
    )
    Path(args.output).write_text(
        json.dumps(draft, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0
