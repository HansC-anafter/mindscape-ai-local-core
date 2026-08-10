import os
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo_root() -> Path:
    return REPO_ROOT


def _mount_targets(volume_entries: list[object]) -> list[str]:
    targets: list[str] = []
    for entry in volume_entries:
        if isinstance(entry, str):
            target = entry.split(":", 1)[-1].split(":", 1)[0]
            targets.append(target)
    return targets


def test_ensure_replication_hba_script_is_idempotent(tmp_path: Path) -> None:
    hba = tmp_path / "pgdata" / "pg_hba.conf"
    hba.parent.mkdir(parents=True, exist_ok=True)
    hba.write_text("local all all all trust\n", encoding="utf-8")

    script = _repo_root() / "docker/postgres/ensure-replication-hba.sh"
    env = os.environ.copy()
    env["PGDATA"] = str(hba.parent)
    env["POSTGRES_USER"] = "mindscape"

    subprocess.run(["sh", str(script)], env=env, check=True, cwd=tmp_path)
    subprocess.run(["sh", str(script)], env=env, check=True, cwd=tmp_path)

    lines = hba.read_text(encoding="utf-8").splitlines()
    assert lines.count("host replication mindscape 0.0.0.0/0 scram-sha-256") == 1
    assert lines.count("host replication mindscape ::/0 scram-sha-256") == 1


def test_postgres_service_recovery_drill_share_hba_reconciliation_artifacts() -> None:
    compose = yaml.safe_load((_repo_root() / "docker-compose.yml").read_text(encoding="utf-8"))
    postgres = compose["services"]["postgres"]

    assert postgres["entrypoint"] == ["/bin/sh", "/opt/mindscape/bootstrap-postgres-entrypoint.sh"]
    volumes = _mount_targets(postgres["volumes"])
    assert "/opt/mindscape/bootstrap-postgres-entrypoint.sh" in volumes
    assert "/opt/mindscape/ensure-replication-hba.sh" in volumes

    recovery = yaml.safe_load(
        (_repo_root() / "docker/compose/postgres-recovery-drill.yml").read_text(encoding="utf-8")
    )
    drill_primary = recovery["services"]["postgres-recovery-drill-primary"]

    assert drill_primary["entrypoint"] == [
        "/bin/sh",
        "/opt/mindscape/bootstrap-postgres-entrypoint.sh",
    ]
    drill_targets = _mount_targets(drill_primary["volumes"])
    assert "/opt/mindscape/bootstrap-postgres-entrypoint.sh" in drill_targets
    assert "/opt/mindscape/ensure-replication-hba.sh" in drill_targets
    assert "/docker-entrypoint-initdb.d/01-ensure-replication-hba.sh" in drill_targets
