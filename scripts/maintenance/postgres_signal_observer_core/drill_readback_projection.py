"""Fixed Docker format projection for disposable drill container readback."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .drill_docker_runtime import canonical_docker_argv
from .drill_names import validate_disposable_drill_name


CONTAINER_READBACK_SCHEMA_VERSION = (
    "mindscape.postgres-signal-observer-container-readback.v1"
)
CONTAINER_READBACK_MAX_BYTES = 32_768
CONTAINER_READBACK_ROLES = frozenset({"postgres", "pgbouncer", "observer", "client"})

_PROJECTION_KEYS = frozenset(
    {
        "schema_version",
        "role",
        "container_id",
        "name",
        "config_image",
        "image_id",
        "user",
        "entrypoint",
        "cmd",
        "nano_cpus",
        "memory_bytes",
        "pids_limit",
        "read_only_rootfs",
        "security_opt",
        "tmpfs",
        "mounts",
        "cap_add",
        "cap_drop",
        "privileged",
        "pid_mode",
        "network_mode",
        "network_id",
        "network_endpoint_id",
        "running",
        "exit_code",
        "restarting",
        "restart_count",
        "started_at",
        "status",
        "paused",
        "dead",
        "oom_killed",
        "health_status",
    }
)

_PROJECTION_TEMPLATE = (
    '{"schema_version":"__SCHEMA__",'
    '"role":"__ROLE__",'
    '"container_id":{{json .ID}},'
    '"name":{{json .Name}},'
    '"config_image":{{json .Config.Image}},'
    '"image_id":{{json .Image}},'
    '"user":{{json .Config.User}},'
    '"entrypoint":{{json .Config.Entrypoint}},'
    '"cmd":{{json .Config.Cmd}},'
    '"nano_cpus":{{json .HostConfig.NanoCPUs}},'
    '"memory_bytes":{{json .HostConfig.Memory}},'
    '"pids_limit":{{json .HostConfig.PidsLimit}},'
    '"read_only_rootfs":{{json .HostConfig.ReadonlyRootfs}},'
    '"security_opt":{{json .HostConfig.SecurityOpt}},'
    '"tmpfs":{{json .HostConfig.Tmpfs}},'
    '"mounts":['
    "{{range $index, $mount := .Mounts}}{{if $index}},{{end}}"
    '{"type":{{json $mount.Type}},'
    '"source":{{json $mount.Source}},'
    '"destination":{{json $mount.Destination}},'
    '"rw":{{json $mount.RW}}}{{end}}],'
    '"cap_add":{{json .HostConfig.CapAdd}},'
    '"cap_drop":{{json .HostConfig.CapDrop}},'
    '"privileged":{{json .HostConfig.Privileged}},'
    '"pid_mode":{{json .HostConfig.PidMode}},'
    '"network_mode":{{json .HostConfig.NetworkMode}},'
    '"network_id":__NETWORK_ID__,'
    '"network_endpoint_id":__NETWORK_ENDPOINT_ID__,'
    '"running":{{json .State.Running}},'
    '"exit_code":{{json .State.ExitCode}},'
    '"restarting":{{json .State.Restarting}},'
    '"restart_count":{{json .RestartCount}},'
    '"started_at":{{json .State.StartedAt}},'
    '"status":{{json .State.Status}},'
    '"paused":{{json .State.Paused}},'
    '"dead":{{json .State.Dead}},'
    '"oom_killed":{{json .State.OOMKilled}},'
    '"health_status":'
    '{{with .State.Health}}{{json .Status}}{{else}}"none"{{end}}}'
)


def _network_projection(path: str, network_name: str | None) -> str:
    if network_name is None:
        return '""'
    validate_disposable_drill_name(network_name)
    return (
        '{{with index .NetworkSettings.Networks "'
        + network_name
        + '"}}{{json .'
        + path
        + '}}{{else}}""{{end}}'
    )


def container_readback_projection_format(
    *,
    role: str,
    attached_network_name: str | None,
) -> str:
    """Return the fixed Docker format projection with no secret-bearing field."""

    if role not in CONTAINER_READBACK_ROLES:
        raise ValueError("drill_container_readback_role_invalid")
    return (
        _PROJECTION_TEMPLATE.replace("__SCHEMA__", CONTAINER_READBACK_SCHEMA_VERSION)
        .replace("__ROLE__", role)
        .replace(
            "__NETWORK_ID__",
            _network_projection("NetworkID", attached_network_name),
        )
        .replace(
            "__NETWORK_ENDPOINT_ID__",
            _network_projection("EndpointID", attached_network_name),
        )
    )


def container_readback_argv(
    *,
    role: str,
    container_name: str,
    attached_network_name: str | None,
) -> tuple[str, ...]:
    """Return the only source-owned container inspect argv."""

    validate_disposable_drill_name(container_name)
    projection = container_readback_projection_format(
        role=role,
        attached_network_name=attached_network_name,
    )
    return canonical_docker_argv(
        "inspect",
        "--type",
        "container",
        "--format",
        projection,
        container_name,
    )


def _string_list_or_none(value: object, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"drill_container_readback_{field}_type_invalid")


def _validate_projection_types(source: Mapping[str, Any]) -> None:
    for field in (
        "schema_version",
        "role",
        "container_id",
        "name",
        "config_image",
        "image_id",
        "user",
        "pid_mode",
        "network_mode",
        "network_id",
        "network_endpoint_id",
        "started_at",
        "status",
        "health_status",
    ):
        if not isinstance(source.get(field), str):
            raise ValueError(f"drill_container_readback_{field}_type_invalid")
    for field in (
        "nano_cpus",
        "memory_bytes",
        "pids_limit",
        "exit_code",
        "restart_count",
    ):
        if type(source.get(field)) is not int:
            raise ValueError(f"drill_container_readback_{field}_type_invalid")
    for field in (
        "read_only_rootfs",
        "privileged",
        "running",
        "restarting",
        "paused",
        "dead",
        "oom_killed",
    ):
        if type(source.get(field)) is not bool:
            raise ValueError(f"drill_container_readback_{field}_type_invalid")
    for field in ("entrypoint", "cmd", "security_opt", "cap_add", "cap_drop"):
        _string_list_or_none(source.get(field), field)
    tmpfs = source.get("tmpfs")
    if tmpfs is not None and (
        not isinstance(tmpfs, dict)
        or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in tmpfs.items()
        )
    ):
        raise ValueError("drill_container_readback_tmpfs_type_invalid")
    mounts = source.get("mounts")
    if not isinstance(mounts, list):
        raise ValueError("drill_container_readback_mounts_type_invalid")
    for mount in mounts:
        if not isinstance(mount, dict) or set(mount) != {
            "type",
            "source",
            "destination",
            "rw",
        }:
            raise ValueError("drill_container_readback_mount_schema_invalid")
        if (
            not isinstance(mount.get("type"), str)
            or not isinstance(mount.get("source"), str)
            or not isinstance(mount.get("destination"), str)
            or type(mount.get("rw")) is not bool
        ):
            raise ValueError("drill_container_readback_mount_type_invalid")


def parse_container_readback_projection(raw_output: bytes) -> dict[str, Any]:
    """Parse one bounded allowlisted line and reject every schema drift."""

    if not isinstance(raw_output, bytes):
        raise TypeError("drill_container_readback_output_bytes_required")
    if not 1 <= len(raw_output) <= CONTAINER_READBACK_MAX_BYTES:
        raise ValueError("drill_container_readback_output_size_invalid")
    if not raw_output.endswith(b"\n") or b"\n" in raw_output[:-1]:
        raise ValueError("drill_container_readback_output_line_invalid")
    try:
        decoded = raw_output[:-1].decode("utf-8")
        source = json.loads(decoded)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("drill_container_readback_output_json_invalid") from exc
    if not isinstance(source, dict) or set(source) != _PROJECTION_KEYS:
        raise ValueError("drill_container_readback_projection_schema_invalid")
    if source.get("schema_version") != CONTAINER_READBACK_SCHEMA_VERSION:
        raise ValueError("drill_container_readback_schema_version_invalid")
    if source.get("role") not in CONTAINER_READBACK_ROLES:
        raise ValueError("drill_container_readback_role_invalid")
    _validate_projection_types(source)
    return dict(source)
