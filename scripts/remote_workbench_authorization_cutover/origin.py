"""Canonical Compose, live container, LAN, and internal-listener origin gate."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from pathlib import Path
from typing import Any, Callable, Mapping

from .io import CommandExecutor, CutoverError, write_private_json
from .origin_mounts import expected_mounts, live_mounts
from .origin_recovery import (
    mark_reconcile_completed,
    persist_reconcile_state,
    recover_persisted_reconcile_state,
    recover_pre_active_services,
)


LOCKED_HOST_BINDINGS = {
    "backend": {
        (8200, "tcp"): 8200,
        **{(port, "tcp"): port for port in range(3002, 3021)},
    },
    "backend-control": {(8210, "tcp"): 8220},
    "frontend": {(3000, "tcp"): 8300},
    "postgres": {(5432, "tcp"): 5433},
    "pgbouncer": {(6432, "tcp"): 6432},
    "postgres-replica": {(5432, "tcp"): 5434},
    "redis": {(6379, "tcp"): 6379},
    "ocr-service": {(8001, "tcp"): 8001},
    "media-proxy": {(8000, "tcp"): 8202},
    "xtts-service": {(8020, "tcp"): 8020},
    "whisper-service": {(8006, "tcp"): 8006},
}


def _default_connectable(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class OriginTopologyGate:
    """Inspect and reconcile only services whose canonical topology drifted."""

    def __init__(
        self,
        *,
        repo_root: Path,
        executor: CommandExecutor,
        connectable: Callable[[str, int, float], bool] = _default_connectable,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.executor = executor
        self.connectable = connectable

    def compose_command(self, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "--project-directory",
            str(self.repo_root),
            "-f",
            str(self.repo_root / "docker-compose.yml"),
            "--profile",
            "control-plane",
            *args,
        ]

    @staticmethod
    def _expand_ports(value: Any) -> set[int]:
        raw = str(value or "")
        if raw.isdigit():
            port = int(raw)
            return {port} if 1 <= port <= 65_535 else set()
        match = re.fullmatch(r"(\d+)-(\d+)", raw)
        if not match:
            return set()
        start, end = (int(part) for part in match.groups())
        if not 1 <= start <= end <= 65_535 or end - start > 100:
            return set()
        return set(range(start, end + 1))

    def _compose_config(self, *, all_profiles: bool = False) -> dict[str, Any]:
        command = self.compose_command("config", "--format", "json")
        if all_profiles:
            profile_index = command.index("control-plane")
            command[profile_index] = "*"
        raw = self.executor.run(
            command,
            timeout_seconds=30.0,
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise CutoverError("Canonical Docker Compose config is malformed") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("services"), dict):
            raise CutoverError("Canonical Docker Compose services are unavailable")
        return payload

    def _require_locked_host_ports(self, config: Mapping[str, Any]) -> None:
        services = config.get("services") or {}
        for name, expected in LOCKED_HOST_BINDINGS.items():
            service = services.get(name)
            if not isinstance(service, Mapping):
                raise CutoverError(f"Locked published service is missing: {name}")
            if self._expected_bindings(service) != expected:
                raise CutoverError(f"Locked published host-port map changed: {name}")

    @staticmethod
    def _expected_bindings(service: Mapping[str, Any]) -> dict[tuple[int, str], int]:
        bindings: dict[tuple[int, str], int] = {}
        for item in service.get("ports") or []:
            if not isinstance(item, Mapping) or item.get("host_ip") != "127.0.0.1":
                raise CutoverError("Every canonical published port must bind to 127.0.0.1")
            published = sorted(OriginTopologyGate._expand_ports(item.get("published")))
            targets = sorted(OriginTopologyGate._expand_ports(item.get("target")))
            protocol = str(item.get("protocol") or "tcp")
            if not published or len(published) != len(targets) or protocol not in {"tcp", "udp"}:
                raise CutoverError("Canonical published port inventory is malformed")
            for target, host_port in zip(targets, published, strict=True):
                key = (target, protocol)
                if key in bindings:
                    raise CutoverError("Canonical container port has duplicate bindings")
                bindings[key] = host_port
        return bindings

    @staticmethod
    def _live_bindings(inspect: Mapping[str, Any]) -> dict[tuple[int, str], tuple[str, int]]:
        bindings = (inspect.get("HostConfig") or {}).get("PortBindings") or {}
        normalized: dict[tuple[int, str], tuple[str, int]] = {}
        for key, values in bindings.items():
            raw_target, separator, protocol = str(key).partition("/")
            targets = sorted(OriginTopologyGate._expand_ports(raw_target))
            if not separator or protocol not in {"tcp", "udp"} or not targets:
                raise CutoverError("Live container port key is malformed")
            if not isinstance(values, list) or len(values) != 1:
                raise CutoverError("Live container port binding is ambiguous")
            for item in values:
                if not isinstance(item, Mapping):
                    raise CutoverError("Live container port binding is malformed")
                host_ports = sorted(OriginTopologyGate._expand_ports(item.get("HostPort")))
                if len(host_ports) != len(targets):
                    raise CutoverError("Live container port range mapping is malformed")
                for target, host_port in zip(targets, host_ports, strict=True):
                    normalized[(target, protocol)] = (str(item.get("HostIp") or ""), host_port)
        return normalized

    @staticmethod
    def _networks(value: Any) -> set[str]:
        if isinstance(value, Mapping):
            return {str(key) for key in value}
        if isinstance(value, list):
            return {str(item) for item in value}
        return set()

    def _inspect_service(
        self,
        service_name: str,
        expected: Mapping[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        container_id = self.executor.run(
            self.compose_command("ps", "-q", service_name),
            timeout_seconds=20.0,
        ).strip()
        if not container_id:
            return {}, ["container_missing"]
        raw = self.executor.run(
            ["docker", "inspect", container_id],
            timeout_seconds=20.0,
        )
        try:
            values = json.loads(raw)
            inspect = values[0]
        except (json.JSONDecodeError, IndexError, TypeError) as error:
            raise CutoverError(f"Docker inspect is malformed for {service_name}") from error
        reasons: list[str] = []
        state = inspect.get("State") or {}
        if state.get("Running") is not True:
            reasons.append("not_running")
        health = state.get("Health")
        if isinstance(health, Mapping) and health.get("Status") != "healthy":
            reasons.append("unhealthy")
        expected_bindings = self._expected_bindings(expected)
        live_bindings = self._live_bindings(inspect)
        expected_live = {
            key: ("127.0.0.1", host_port)
            for key, host_port in expected_bindings.items()
        }
        if live_bindings != expected_live:
            reasons.append("port_bindings")
        config = inspect.get("Config") or {}
        expected_image = expected.get("image")
        if expected_image is not None and str(config.get("Image") or "") != str(expected_image):
            reasons.append("image")
        expected_command = expected.get("command")
        if expected_command is not None and config.get("Cmd") != expected_command:
            reasons.append("command")
        expected_networks = self._networks(expected.get("networks"))
        live_networks = self._networks((inspect.get("NetworkSettings") or {}).get("Networks"))
        if expected_networks != live_networks:
            reasons.append("networks")
        expected_mount_inventory = expected_mounts(expected)
        live_mount_inventory = live_mounts(inspect)
        if live_mount_inventory != expected_mount_inventory:
            reasons.append("bind_mounts")
        labels = config.get("Labels") or {}
        if labels.get("com.docker.compose.project") != "mindscape-ai-local-core":
            reasons.append("compose_project")
        if labels.get("com.docker.compose.service") != service_name:
            reasons.append("compose_service")
        if labels.get("com.docker.compose.project.working_dir") != str(self.repo_root):
            reasons.append("working_directory")
        evidence = {
            "container_id": container_id,
            "image": config.get("Image"),
            "cmd": config.get("Cmd"),
            "host_config": {"port_bindings": (inspect.get("HostConfig") or {}).get("PortBindings")},
            "networks": sorted(live_networks),
            "mounts": live_mount_inventory,
            "live_host_ports": sorted(host_port for _host, host_port in live_bindings.values()),
            "drift": sorted(set(reasons)),
        }
        return evidence, reasons

    def _lan_hosts(self) -> list[str]:
        raw = self.executor.run(["ifconfig"], timeout_seconds=10.0)
        hosts = []
        for value in re.findall(r"^\s*inet\s+(\d+\.\d+\.\d+\.\d+)\b", raw, re.MULTILINE):
            try:
                parsed = ipaddress.ip_address(value)
            except ValueError:
                continue
            if not parsed.is_loopback and not parsed.is_unspecified and not parsed.is_link_local:
                hosts.append(value)
        hosts = sorted(set(hosts))
        if not hosts:
            raise CutoverError("No active non-loopback IPv4 interface is available")
        return hosts

    def _active_services(self, project_name: str) -> set[str]:
        raw = self.executor.run(
            [
                "docker",
                "ps",
                "--filter",
                f"label=com.docker.compose.project={project_name}",
                "--format",
                "{{.Label \"com.docker.compose.service\"}}",
            ],
            timeout_seconds=20.0,
        )
        return {line.strip() for line in raw.splitlines() if line.strip()}

    def _internal_listener_probe(self, workspace_id: str) -> dict[str, Any]:
        script = """
const http=require('http');
const hosts=['spoof.invalid','localhost','remote-workbench.mindscapeai.app'];
const run=(host)=>new Promise((resolve)=>{const req=http.request({host:'127.0.0.1',port:3001,path:process.argv[1],headers:{Host:host}},(res)=>{res.resume();res.on('end',()=>resolve({host,status:res.statusCode,stage:res.headers['x-mindscape-remote-auth-stage']||null,reason:res.headers['x-mindscape-remote-auth-reason']||null}));});req.on('error',(error)=>resolve({host,closed:error.code||'unreachable'}));req.end();});
Promise.all(hosts.map(run)).then((rows)=>process.stdout.write(JSON.stringify(rows)));
""".strip()
        raw = self.executor.run(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-frontend",
                "node",
                "-e",
                script,
                f"/workspaces/{workspace_id}",
            ],
            timeout_seconds=15.0,
        )
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError as error:
            raise CutoverError("Internal remote listener probe is malformed") from error
        if not isinstance(rows, list) or len(rows) != 3:
            raise CutoverError("Internal remote listener probe shape is invalid")
        if all(isinstance(row, dict) and row.get("closed") for row in rows):
            return {"state": "closed", "rows": rows}
        expected_reasons = {
            "spoof.invalid": "invalid_public_host",
            "localhost": "invalid_public_host",
            "remote-workbench.mindscapeai.app": "missing_access_token",
        }
        for row in rows:
            if (
                not isinstance(row, dict)
                or row.get("status") != 403
                or row.get("stage") != "identity_rejected"
                or row.get("reason") != expected_reasons.get(row.get("host"))
            ):
                raise CutoverError("Internal remote listener did not default deny")
        return {"state": "default_deny", "rows": rows}

    def inspect(self, secure_dir: Path, workspace_id: str) -> dict[str, Any]:
        """Return exact drift inventory and save read-only preflight evidence."""

        config = self._compose_config()
        all_config = self._compose_config(all_profiles=True)
        self._require_locked_host_ports(all_config)
        project_name = str(config.get("name") or "mindscape-ai-local-core")
        active_services = self._active_services(project_name)
        all_services = all_config["services"]
        unknown_active = active_services.difference(all_services)
        if unknown_active:
            raise CutoverError("Active Compose project contains an unknown service identity")
        services = {
            name: service
            for name, service in config["services"].items()
            if isinstance(service, Mapping) and self._expected_bindings(service)
        }
        for name in active_services:
            services[name] = all_services[name]
        service_evidence: dict[str, Any] = {}
        drift: dict[str, list[str]] = {}
        port_owner: dict[int, str] = {}
        for name, service in services.items():
            if not isinstance(service, Mapping):
                raise CutoverError("Canonical Compose service is malformed")
            expected_bindings = self._expected_bindings(service)
            for port in expected_bindings.values():
                if port in port_owner:
                    raise CutoverError("Canonical published port has multiple owners")
                port_owner[port] = name
            evidence, reasons = self._inspect_service(name, service)
            evidence["drift"] = sorted(set(reasons))
            service_evidence[name] = evidence
            for port in evidence.get("live_host_ports") or []:
                existing_owner = port_owner.get(port)
                if existing_owner not in (None, name):
                    raise CutoverError("Live published port has multiple owners")
                port_owner[port] = name
            if reasons:
                drift[name] = sorted(set(reasons))
        lan_hosts = self._lan_hosts()
        reachable = []
        for lan_host in lan_hosts:
            for port, owner in sorted(port_owner.items()):
                if self.connectable(lan_host, port, 0.25):
                    reachable.append({"host": lan_host, "port": port})
                    drift.setdefault(owner, []).append("lan_reachable")
        frontend_drift = set((service_evidence.get("frontend") or {}).get("drift") or [])
        if frontend_drift.intersection({"container_missing", "not_running"}):
            listener = {
                "state": "closed",
                "reason": "frontend_unavailable_before_reconcile",
            }
        else:
            listener = self._internal_listener_probe(workspace_id)
        payload = {
            "canonical_repo": str(self.repo_root),
            "published_ports": sorted(port_owner),
            "lan_hosts": lan_hosts,
            "lan_reachable_ports": reachable,
            "services": service_evidence,
            "drift": {key: sorted(set(value)) for key, value in sorted(drift.items())},
            "internal_listener": listener,
        }
        write_private_json(secure_dir / "origin-topology-inspect.json", payload)
        return payload

    def reconcile(
        self,
        drift: Mapping[str, Any],
        *,
        secure_dir: Path,
        workspace_id: str,
    ) -> dict[str, Any]:
        """Recreate only drifted services, then require a closed topology."""

        services = sorted(str(name) for name in drift)
        if services:
            config = self._compose_config(all_profiles=True)
            all_services = set(config["services"])
            infra = {"postgres", "postgres-replica", "redis", "pgbouncer"}
            stopped_dependents: list[str] = []
            active_services = self._active_services(
                str(config.get("name") or "mindscape-ai-local-core")
            )
            if infra.intersection(services):
                stopped_dependents = sorted(
                    name
                    for name in active_services.intersection(all_services)
                    if (
                        name in {"backend", "backend-control", "frontend"}
                        or name.startswith("runner")
                    )
                )
            before = persist_reconcile_state(
                self,
                secure_dir=secure_dir,
                active_services=active_services,
                mutated_services=services,
                stopped_dependents=stopped_dependents,
            )
            ordered_groups = [
                [name for name in ("postgres", "postgres-replica", "redis") if name in services],
                ["pgbouncer"] if "pgbouncer" in services else [],
                [
                    name
                    for name in services
                    if name not in infra
                    and name not in {"backend", "backend-control", "frontend"}
                    and not name.startswith("runner")
                ],
                [name for name in ("backend", "backend-control", "frontend") if name in services],
                [name for name in services if name.startswith("runner")],
            ]
            try:
                if stopped_dependents:
                    self.executor.run(
                        self.compose_command("stop", *stopped_dependents),
                        timeout_seconds=180.0,
                    )
                for group in ordered_groups:
                    if not group:
                        continue
                    self.executor.run(
                        self.compose_command(
                            "up", "-d", "--force-recreate", "--no-deps", *group
                        ),
                        timeout_seconds=300.0,
                    )
                restart = [name for name in stopped_dependents if name not in services]
                if restart:
                    self.executor.run(
                        self.compose_command("up", "-d", "--no-deps", *restart),
                        timeout_seconds=300.0,
                    )
                result = self.inspect(secure_dir, workspace_id)
                if result.get("drift") or result.get("lan_reachable_ports"):
                    raise CutoverError(
                        "Canonical origin topology remains drifted after reconcile"
                    )
                write_private_json(secure_dir / "origin-topology-after.json", result)
                mark_reconcile_completed(secure_dir)
                return result
            except Exception as failure:
                try:
                    recover_pre_active_services(
                        self,
                        config=config,
                        pre_active_services=active_services,
                        mutated_services=services,
                        stopped_dependents=stopped_dependents,
                        before=before,
                    )
                except Exception as recovery_error:
                    raise CutoverError("Origin reconcile recovery failed closed") from recovery_error
                raise failure
        result = self.inspect(secure_dir, workspace_id)
        if result.get("drift") or result.get("lan_reachable_ports"):
            raise CutoverError("Canonical origin topology remains drifted after reconcile")
        write_private_json(secure_dir / "origin-topology-after.json", result)
        return result

    def recover_persisted(self, secure_dir: Path) -> bool:
        return recover_persisted_reconcile_state(self, secure_dir)
