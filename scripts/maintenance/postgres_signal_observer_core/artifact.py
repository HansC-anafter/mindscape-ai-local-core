"""Canonical digest for the exact signal-observer executable source."""

from __future__ import annotations

import hashlib
from pathlib import Path


OBSERVER_SOURCE_PATHS = (
    "backend/app/services/runtime_database_incident_gate.py",
    "backend/app/services/runtime_database_incident_core/evaluator.py",
    "backend/app/services/runtime_database_incident_core/journal.py",
    "backend/app/services/runtime_database_incident_core/models.py",
    "backend/app/services/runtime_database_incident_core/mutation_context.py",
    "docker/postgres/Dockerfile",
    "scripts/maintenance/postgres_incident_gate.py",
    "scripts/maintenance/postgres_signal_observer.py",
    "scripts/maintenance/postgres_signal_observer_drill.py",
    "scripts/maintenance/postgres_signal_observer_ownership_grant.py",
    "scripts/maintenance/postgres_signal_observer_core/__init__.py",
    "scripts/maintenance/postgres_signal_observer_core/artifact.py",
    "scripts/maintenance/postgres_signal_observer_core/drill.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_admin_url.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_bootstrap.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_docker_runtime.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_escalation.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_formal_cli.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_formal_contract.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_formal_executor.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_formal_gates.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_formal_sequence.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_formal_terminal.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_gate_receipt.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_images.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_names.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_observer.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_observer_launch_receipt.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_pgbouncer_gate_receipt.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_pgbouncer_readiness.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_preconditions.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_readback.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_readback_projection.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_readiness_stage.py",
    "scripts/maintenance/postgres_signal_observer_core/drill_runtime.py",
    "scripts/maintenance/postgres_signal_observer_core/evidence.py",
    "scripts/maintenance/postgres_signal_observer_core/events.py",
    "scripts/maintenance/postgres_signal_observer_core/pgbouncer.py",
    "scripts/maintenance/postgres_signal_observer_core/service.py",
    "scripts/maintenance/postgres_signal_observer_core/tracefs.py",
    "scripts/maintenance/postgres_signal_observer_preflight.py",
    "scripts/maintenance/postgres_signal_observer_preflight_core/__init__.py",
    "scripts/maintenance/postgres_signal_observer_preflight_core/permit_binding.py",
    "scripts/maintenance/postgres_signal_observer_preflight_core/preflight.py",
)


def canonical_observer_artifact_sha256(repo_root: Path) -> str:
    digest = hashlib.sha256()
    root = Path(repo_root).resolve()
    for relative in OBSERVER_SOURCE_PATHS:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"observer_source_unavailable:{relative}")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
