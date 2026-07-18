from __future__ import annotations

import json

import pytest

from scripts.maintenance.postgres_signal_observer_core.drill_readback_projection import (
    CONTAINER_READBACK_SCHEMA_VERSION,
    container_readback_argv,
    parse_container_readback_projection,
)


DRILL_SUFFIX = "20260718t202456z"
NETWORK_NAME = f"runtime-db-observer-drill-{DRILL_SUFFIX}"
SENTINEL_SECRET = "sentinel-secret-must-never-enter-projection"

_MOUNTS_TEMPLATE = (
    "{{range $index, $mount := .Mounts}}{{if $index}},{{end}}"
    '{"type":{{json $mount.Type}},'
    '"source":{{json $mount.Source}},'
    '"destination":{{json $mount.Destination}},'
    '"rw":{{json $mount.RW}}}{{end}}'
)

_PROJECTION_TOKENS = {
    "{{json .Id}}": "container_id",
    "{{json .Name}}": "name",
    "{{json .Config.Image}}": "config_image",
    "{{json .Image}}": "image_id",
    "{{json .Config.User}}": "user",
    "{{json .Config.Entrypoint}}": "entrypoint",
    "{{json .Config.Cmd}}": "cmd",
    "{{json .HostConfig.NanoCpus}}": "nano_cpus",
    "{{json .HostConfig.Memory}}": "memory_bytes",
    "{{json .HostConfig.PidsLimit}}": "pids_limit",
    "{{json .HostConfig.ReadonlyRootfs}}": "read_only_rootfs",
    "{{json .HostConfig.SecurityOpt}}": "security_opt",
    "{{json .HostConfig.Tmpfs}}": "tmpfs",
    "{{json .HostConfig.CapAdd}}": "cap_add",
    "{{json .HostConfig.CapDrop}}": "cap_drop",
    "{{json .HostConfig.Privileged}}": "privileged",
    "{{json .HostConfig.PidMode}}": "pid_mode",
    "{{json .HostConfig.NetworkMode}}": "network_mode",
    "{{json .State.Running}}": "running",
    "{{json .State.ExitCode}}": "exit_code",
    "{{json .State.Restarting}}": "restarting",
    "{{json .RestartCount}}": "restart_count",
    "{{json .State.StartedAt}}": "started_at",
    "{{json .State.Status}}": "status",
    "{{json .State.Paused}}": "paused",
    "{{json .State.Dead}}": "dead",
    "{{json .State.OOMKilled}}": "oom_killed",
}


def _fixture(role: str, attached_network_name: str | None) -> dict[str, object]:
    attached = attached_network_name is not None
    return {
        "schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
        "role": role,
        "container_id": "a" * 64,
        "name": f"/runtime-db-observer-drill-{role}-{DRILL_SUFFIX}",
        "config_image": "canonical-image@sha256:" + "b" * 64,
        "image_id": "sha256:" + "c" * 64,
        "user": "postgres",
        "entrypoint": ["docker-entrypoint.sh"],
        "cmd": ["postgres"],
        "nano_cpus": 100_000_000,
        "memory_bytes": 67_108_864,
        "pids_limit": 16,
        "read_only_rootfs": True,
        "security_opt": ["no-new-privileges:true"],
        "tmpfs": {"/tmp": "rw,noexec,nosuid,size=4m"},
        "mounts": [],
        "cap_add": None,
        "cap_drop": ["ALL"],
        "privileged": False,
        "pid_mode": "",
        "network_mode": attached_network_name or "none",
        "network_id": "d" * 64 if attached else "",
        "network_endpoint_id": "e" * 64 if attached else "",
        "running": True,
        "exit_code": 0,
        "restarting": False,
        "restart_count": 0,
        "started_at": "2026-07-18T20:25:24.000000000Z",
        "status": "running",
        "paused": False,
        "dead": False,
        "oom_killed": False,
        "health_status": "none",
    }


def _render_production_template(
    projection: str,
    fixture: dict[str, object],
    attached_network_name: str | None,
) -> bytes:
    rendered = projection.replace(_MOUNTS_TEMPLATE, "")
    for token, field in _PROJECTION_TOKENS.items():
        rendered = rendered.replace(
            token,
            json.dumps(fixture[field], separators=(",", ":")),
        )
    rendered = rendered.replace(
        '{{with .State.Health}}{{json .Status}}{{else}}"none"{{end}}',
        json.dumps(fixture["health_status"]),
    )
    if attached_network_name is not None:
        for path, field in (
            ("NetworkID", "network_id"),
            ("EndpointID", "network_endpoint_id"),
        ):
            rendered = rendered.replace(
                '{{with index .NetworkSettings.Networks "'
                + attached_network_name
                + '"}}{{json .'
                + path
                + '}}{{else}}""{{end}}',
                json.dumps(fixture[field]),
            )
    return rendered.encode("utf-8") + b"\n"


@pytest.mark.parametrize("role", ("postgres", "pgbouncer", "observer", "client"))
@pytest.mark.parametrize("attached_network_name", (None, NETWORK_NAME))
def test_production_projection_argv_and_parser_parity(
    role: str,
    attached_network_name: str | None,
) -> None:
    argv = container_readback_argv(
        role=role,
        container_name=f"runtime-db-observer-drill-{role}-{DRILL_SUFFIX}",
        attached_network_name=attached_network_name,
    )
    projection = argv[5]

    assert projection.startswith("{")
    assert projection.endswith("}")
    assert "__" not in projection
    assert ".Config.Env" not in projection
    assert ".Config.Labels" not in projection
    assert "{{json .Config}}" not in projection
    assert "{{json .State}}" not in projection
    assert SENTINEL_SECRET not in projection

    fixture = _fixture(role, attached_network_name)
    rendered = _render_production_template(
        projection,
        fixture,
        attached_network_name,
    )

    assert b"{{" not in rendered
    assert parse_container_readback_projection(rendered) == fixture

