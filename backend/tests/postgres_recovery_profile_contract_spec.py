from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _profiles(service: dict[str, object]) -> set[str]:
    value = service.get("profiles") or []
    return set(value)


def test_recovery_drill_and_disposable_restore_profiles_are_isolated() -> None:
    compose = yaml.safe_load(
        (REPO_ROOT / "docker/compose/postgres-recovery-drill.yml").read_text(
            encoding="utf-8"
        )
    )
    services = compose["services"]

    drill_services = {
        "postgres-recovery-drill-primary",
        "postgres-recovery-drill-standby",
        "pgbouncer-recovery-drill",
    }
    restore_services = {
        "postgres-recovery-restore",
        "postgres-recovery-restore-app-probe",
    }

    for name in drill_services:
        assert _profiles(services[name]) == {"postgres-recovery-drill"}
    for name in restore_services:
        assert _profiles(services[name]) == {"postgres-disposable-restore"}
