"""Exact source-contract comparison for candidate migration admission."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


_IGNORED_PARTS = {"__pycache__"}
_IGNORED_SUFFIXES = {".pyc", ".pyo"}


@dataclass(frozen=True)
class MigrationContractDigest:
    """Deterministic receipt for one capability migration source contract."""

    sha256: str
    file_count: int


def _contract_files(capability_dir: Path) -> list[Path]:
    files: list[Path] = []
    metadata = capability_dir / "migrations.yaml"
    if metadata.is_file():
        files.append(metadata)

    migrations_dir = capability_dir / "migrations"
    if migrations_dir.is_dir():
        files.extend(
            path
            for path in migrations_dir.rglob("*")
            if path.is_file()
            and not any(part in _IGNORED_PARTS for part in path.parts)
            and path.suffix not in _IGNORED_SUFFIXES
        )
    return sorted(files, key=lambda path: path.relative_to(capability_dir).as_posix())


def digest_migration_contract(capability_dir: Path) -> MigrationContractDigest:
    """Hash migration metadata, relative paths, and bytes without runtime caches."""

    digest = hashlib.sha256()
    files = _contract_files(capability_dir)
    for path in files:
        relative = path.relative_to(capability_dir).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return MigrationContractDigest(
        sha256=digest.hexdigest(),
        file_count=len(files),
    )


def equivalent_migration_contracts(
    candidate_capability_dir: Path,
    installed_capability_dir: Path,
) -> tuple[bool, MigrationContractDigest, MigrationContractDigest]:
    """Return exact source equivalence; missing installed capability is never equal."""

    candidate = digest_migration_contract(candidate_capability_dir)
    installed = digest_migration_contract(installed_capability_dir)
    equivalent = (
        installed_capability_dir.is_dir()
        and candidate.file_count == installed.file_count
        and candidate.sha256 == installed.sha256
    )
    return equivalent, candidate, installed
