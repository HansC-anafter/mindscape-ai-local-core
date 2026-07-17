from pathlib import Path

from backend.app.routes.core.capability_install_core.install_commit_core.requirement_preflight import (
    validate_atomic_install_requirements,
)


def test_atomic_preflight_rejects_mutating_bootstrap_before_publish(tmp_path: Path):
    blockers = validate_atomic_install_requirements(
        local_core_root=tmp_path,
        candidate_dir=tmp_path / "candidate",
        manifest={"bootstrap": [{"type": "python_script", "path": "seed.py"}]},
    )

    assert blockers == ["bootstrap_not_atomic:0:python_script"]


def test_atomic_preflight_accepts_pack_without_runtime_mutations(tmp_path: Path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    blockers = validate_atomic_install_requirements(
        local_core_root=tmp_path,
        candidate_dir=candidate,
        manifest={"playbooks": []},
    )

    assert blockers == []
