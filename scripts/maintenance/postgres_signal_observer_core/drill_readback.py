"""Exact validation and execution for bounded drill container readback."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Mapping

from .drill_docker_runtime import validate_canonical_docker_argv
from .drill_images import (
    OBSERVER_BACKEND_IMAGE_ROLE,
    POSTGRES_DRILL_IMAGE_ROLE,
    drill_image_digest,
    validate_drill_image_ref,
)
from .drill_names import validate_disposable_drill_name
from .drill_readback_projection import (
    CONTAINER_READBACK_MAX_BYTES,
    CONTAINER_READBACK_ROLES,
    CONTAINER_READBACK_SCHEMA_VERSION,
    container_readback_argv,
    parse_container_readback_projection,
)


CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS = 10.0
_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
_STARTED_AT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+(?:Z|[+-][0-9:]+)$")
_VALUE_OPTIONS = frozenset(
    {
        "--name",
        "--network",
        "--network-alias",
        "--cpus",
        "--memory",
        "--pids-limit",
        "--tmpfs",
        "--security-opt",
        "--env",
        "--mount",
        "--user",
        "--entrypoint",
        "--restart",
        "--pid",
        "--cap-drop",
        "--cap-add",
        "--health-cmd",
        "--health-interval",
        "--health-timeout",
        "--health-retries",
        "--health-start-period",
        "--log-driver",
        "--log-opt",
    }
)
_FLAG_OPTIONS = frozenset({"-d", "--read-only", "--init", "--privileged"})


def _memory_bytes(value: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)([kmgt]?)", value.lower())
    if match is None:
        raise ValueError("drill_container_readback_memory_budget_invalid")
    scale = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    return int(match.group(1)) * scale[match.group(2)]


def _mount_contract(value: str) -> dict[str, object]:
    fields: dict[str, str] = {}
    readonly = False
    for item in value.split(","):
        if item == "readonly":
            readonly = True
            continue
        if "=" not in item:
            raise ValueError("drill_container_readback_mount_contract_invalid")
        key, field_value = item.split("=", 1)
        fields[key] = field_value
    if set(fields) != {"type", "src", "dst"} or fields["type"] != "bind":
        raise ValueError("drill_container_readback_mount_contract_invalid")
    return {
        "type": "bind",
        "source": fields["src"],
        "destination": fields["dst"],
        "rw": not readonly,
    }


def _option_values(options: Mapping[str, list[str]], option: str) -> list[str]:
    return list(options.get(option, []))


def _single_option(
    options: Mapping[str, list[str]],
    option: str,
    *,
    default: str,
) -> str:
    values = _option_values(options, option)
    if len(values) > 1:
        raise ValueError("drill_container_readback_run_argv_invalid")
    return values[0] if values else default


def _parse_run_argv(
    run_argv: tuple[str, ...],
    image_ref: str,
) -> tuple[dict[str, list[str]], frozenset[str], list[str]]:
    exact_argv = validate_canonical_docker_argv(run_argv)
    if exact_argv[1:3] != ("run", "-d") or image_ref not in exact_argv:
        raise ValueError("drill_container_readback_run_argv_invalid")
    image_index = exact_argv.index(image_ref)
    options: dict[str, list[str]] = {}
    flags: set[str] = {"-d"}
    index = 3
    while index < image_index:
        option = exact_argv[index]
        if option in _FLAG_OPTIONS:
            flags.add(option)
            index += 1
            continue
        if option not in _VALUE_OPTIONS or index + 1 >= image_index:
            raise ValueError("drill_container_readback_run_argv_invalid")
        options.setdefault(option, []).append(exact_argv[index + 1])
        index += 2
    return options, frozenset(flags), list(exact_argv[image_index + 1 :])


@dataclass(frozen=True)
class DisposableDrillContainerReadbackContract:
    """Exact expected projection derived from one source-owned run argv."""

    role: str
    run_argv: tuple[str, ...]
    image_ref: str

    def _expected(self) -> dict[str, object]:
        if self.role not in CONTAINER_READBACK_ROLES:
            raise ValueError("drill_container_readback_role_invalid")
        image_role = (
            OBSERVER_BACKEND_IMAGE_ROLE
            if self.role == "observer"
            else POSTGRES_DRILL_IMAGE_ROLE
        )
        validate_drill_image_ref(self.image_ref, role=image_role)
        options, flags, command = _parse_run_argv(self.run_argv, self.image_ref)
        container_name = _single_option(options, "--name", default="")
        validate_disposable_drill_name(container_name)
        network_mode = _single_option(options, "--network", default="default")
        attached_network_name = (
            None if network_mode.startswith("container:") else network_mode
        )
        if attached_network_name is not None:
            validate_disposable_drill_name(attached_network_name)
        entrypoint = _single_option(options, "--entrypoint", default="")
        if not entrypoint and self.role == "postgres":
            entrypoint = "docker-entrypoint.sh"
        if not command and self.role == "postgres":
            command = ["postgres"]
        tmpfs: dict[str, str] = {}
        for value in _option_values(options, "--tmpfs"):
            path, separator, contract = value.partition(":")
            if not separator or not path or not contract or path in tmpfs:
                raise ValueError("drill_container_readback_tmpfs_contract_invalid")
            tmpfs[path] = contract
        return {
            "role": self.role,
            "name": f"/{container_name}",
            "config_image": self.image_ref,
            "image_id": drill_image_digest(self.image_ref, role=image_role),
            "user": _single_option(options, "--user", default=""),
            "entrypoint": [entrypoint] if entrypoint else None,
            "cmd": command or None,
            "nano_cpus": int(
                float(_single_option(options, "--cpus", default="0")) * 1_000_000_000
            ),
            "memory_bytes": _memory_bytes(
                _single_option(options, "--memory", default="0")
            ),
            "pids_limit": int(_single_option(options, "--pids-limit", default="0")),
            "read_only_rootfs": "--read-only" in flags,
            "security_opt": _option_values(options, "--security-opt") or None,
            "tmpfs": tmpfs or None,
            "mounts": [
                _mount_contract(value) for value in _option_values(options, "--mount")
            ],
            "cap_add": _option_values(options, "--cap-add") or None,
            "cap_drop": _option_values(options, "--cap-drop") or None,
            "privileged": "--privileged" in flags,
            "pid_mode": _single_option(options, "--pid", default=""),
            "network_mode": network_mode,
            "attached_network_name": attached_network_name,
            "has_healthcheck": bool(_option_values(options, "--health-cmd")),
        }

    def inspect_argv(self) -> tuple[str, ...]:
        expected = self._expected()
        network_name = expected["attached_network_name"]
        return container_readback_argv(
            role=self.role,
            container_name=str(expected["name"])[1:],
            attached_network_name=(
                str(network_name) if isinstance(network_name, str) else None
            ),
        )

    def validate_projection(self, source: Mapping[str, Any]) -> dict[str, Any]:
        expected = self._expected()
        failures: list[str] = []
        for field in (
            "role",
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
        ):
            if source.get(field) != expected[field]:
                failures.append(f"{self.role}_container_readback_{field}_mismatch")
        attached_network_name = expected["attached_network_name"]
        network_ids_ok = bool(
            attached_network_name is None
            and source.get("network_id") == ""
            and source.get("network_endpoint_id") == ""
        ) or bool(
            isinstance(attached_network_name, str)
            and _CONTAINER_ID.fullmatch(str(source.get("network_id") or ""))
            and _CONTAINER_ID.fullmatch(str(source.get("network_endpoint_id") or ""))
        )
        if not network_ids_ok:
            failures.append(f"{self.role}_container_readback_network_identity_mismatch")
        if not _CONTAINER_ID.fullmatch(str(source.get("container_id") or "")):
            failures.append(f"{self.role}_container_readback_id_invalid")
        state_ok = bool(
            source.get("running") is True
            and source.get("exit_code") == 0
            and source.get("restarting") is False
            and source.get("restart_count") == 0
            and source.get("status") == "running"
            and source.get("paused") is False
            and source.get("dead") is False
            and source.get("oom_killed") is False
            and _STARTED_AT.fullmatch(str(source.get("started_at") or ""))
        )
        if not state_ok:
            failures.append(f"{self.role}_container_readback_state_unready")
        health_status = source.get("health_status")
        health_ok = (
            health_status in {"starting", "healthy"}
            if expected["has_healthcheck"] is True
            else health_status == "none"
        )
        if not health_ok:
            failures.append(f"{self.role}_container_readback_health_mismatch")
        return {
            "validation_passed": not failures,
            "first_failure": failures[0] if failures else None,
            "failures": failures,
            "role": self.role,
            "container_started": state_ok,
            "application_readiness_owner": (
                "canonical_observer_health_journal"
                if self.role == "observer"
                else "existing_role_specific_readiness_gate"
            ),
            "projection": dict(source),
        }


def execute_disposable_container_readback(
    contract: DisposableDrillContainerReadbackContract,
    *,
    run: Any = subprocess.run,
) -> dict[str, Any]:
    """Execute one bounded projection and never persist raw Docker payload."""

    argv = contract.inspect_argv()
    base = {
        "validation_passed": False,
        "first_failure": None,
        "failures": [],
        "role": contract.role,
        "inspect_argv": list(argv),
        "inspect_argv_sha256": hashlib.sha256(
            "\0".join(argv).encode("utf-8")
        ).hexdigest(),
        "projection_schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
        "projection_max_bytes": CONTAINER_READBACK_MAX_BYTES,
        "terminal_deadline_seconds": CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS,
        "raw_inspect_json_captured": False,
        "config_env_captured": False,
        "secret_value_or_hash_persisted": False,
        "shell": False,
    }
    try:
        completed = run(
            list(argv),
            check=False,
            capture_output=True,
            text=False,
            timeout=CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        failure = f"formal_{contract.role}_readback_terminal_deadline_exceeded"
        return {**base, "first_failure": failure, "failures": [failure]}
    except OSError:
        failure = f"formal_{contract.role}_readback_unavailable"
        return {**base, "first_failure": failure, "failures": [failure]}
    if type(getattr(completed, "returncode", None)) is not int:
        failure = f"formal_{contract.role}_readback_result_invalid"
        return {**base, "first_failure": failure, "failures": [failure]}
    if completed.returncode != 0:
        failure = f"formal_{contract.role}_readback_failed"
        return {**base, "first_failure": failure, "failures": [failure]}
    raw_output = getattr(completed, "stdout", None)
    try:
        projection = parse_container_readback_projection(raw_output)
    except (TypeError, ValueError):
        failure = f"formal_{contract.role}_readback_projection_invalid"
        return {**base, "first_failure": failure, "failures": [failure]}
    receipt = contract.validate_projection(projection)
    output_bytes = bytes(raw_output)
    return {
        **base,
        **receipt,
        "projection_bytes": len(output_bytes),
        "projection_sha256": hashlib.sha256(output_bytes).hexdigest(),
    }
