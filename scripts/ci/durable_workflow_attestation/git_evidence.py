"""Read committed Git identities without scanning working-tree content."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .models import AttestationInputError, REPO_IDS, RepositoryEvidence


def _git(repo: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AttestationInputError(f"git evidence failed for {repo}: {exc}") from exc
    return completed.stdout.strip()


def collect_repository_evidence(
    *,
    repo_id: str,
    repo_path: Path,
) -> RepositoryEvidence:
    if repo_id not in REPO_IDS:
        raise AttestationInputError(f"unsupported repository identity: {repo_id}")
    path = repo_path.resolve()
    if _git(path, "status", "--porcelain=v1", "--untracked-files=all"):
        raise AttestationInputError(
            f"{repo_id} working tree is dirty; attestation accepts committed trees only"
        )
    return RepositoryEvidence(
        repo_id=repo_id,
        commit_sha=_git(path, "rev-parse", "HEAD"),
        tree_sha=_git(path, "rev-parse", "HEAD^{tree}"),
    )
