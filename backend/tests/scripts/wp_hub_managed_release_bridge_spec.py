"""Static contract tests for the one wp-hub SSH bridge."""

from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path

import pytest
import yaml


def _module():
    path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "wp_hub_managed_release_bridge.py"
    )
    spec = importlib.util.spec_from_file_location("wp_hub_bridge", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bridge_builds_one_noninteractive_host_key_pinned_ssh_path(
    tmp_path,
    monkeypatch,
):
    module = _module()
    identity = tmp_path / "id"
    known_hosts = tmp_path / "known_hosts"
    identity.write_text("identity", encoding="utf-8")
    known_hosts.write_text("host-key", encoding="utf-8")
    identity.chmod(0o600)
    known_hosts.chmod(0o644)
    values = {
        "WP_HUB_RELEASE_SSH_HOST": "wp-hub.example.test",
        "WP_HUB_RELEASE_SSH_USER": "release",
        "WP_HUB_RELEASE_SSH_PORT": "22",
        "WP_HUB_RELEASE_SSH_IDENTITY_FILE": str(identity),
        "WP_HUB_RELEASE_SSH_IDENTITY_SHA256": hashlib.sha256(
            identity.read_bytes()
        ).hexdigest(),
        "WP_HUB_RELEASE_SSH_KNOWN_HOSTS_FILE": str(known_hosts),
        "WP_HUB_RELEASE_SSH_KNOWN_HOSTS_SHA256": hashlib.sha256(
            known_hosts.read_bytes()
        ).hexdigest(),
        "WP_HUB_RELEASE_REMOTE_EXECUTABLE": (
            "/opt/wp-hub/bin/wp-site-release-adapter"
        ),
        "WP_HUB_RELEASE_REMOTE_EXECUTABLE_SHA256": "a" * 64,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    config = module._configuration()
    command = module._ssh_base(config)

    assert command[0] == "/usr/bin/ssh"
    assert "BatchMode=yes" in command
    assert "StrictHostKeyChecking=yes" in command
    assert "ClearAllForwardings=yes" in command
    assert command[-1] == "release@wp-hub.example.test"


def test_bridge_rejects_remote_shell_metacharacters(
    tmp_path,
    monkeypatch,
):
    module = _module()
    identity = tmp_path / "id"
    known_hosts = tmp_path / "known_hosts"
    identity.write_text("identity", encoding="utf-8")
    known_hosts.write_text("host-key", encoding="utf-8")
    identity.chmod(0o600)
    known_hosts.chmod(0o600)
    monkeypatch.setenv("WP_HUB_RELEASE_SSH_HOST", "example.test")
    monkeypatch.setenv("WP_HUB_RELEASE_SSH_USER", "release")
    monkeypatch.setenv("WP_HUB_RELEASE_SSH_IDENTITY_FILE", str(identity))
    monkeypatch.setenv(
        "WP_HUB_RELEASE_SSH_IDENTITY_SHA256",
        hashlib.sha256(identity.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "WP_HUB_RELEASE_SSH_KNOWN_HOSTS_FILE",
        str(known_hosts),
    )
    monkeypatch.setenv(
        "WP_HUB_RELEASE_SSH_KNOWN_HOSTS_SHA256",
        hashlib.sha256(known_hosts.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv(
        "WP_HUB_RELEASE_REMOTE_EXECUTABLE",
        "/opt/wp-hub/bin/adapter;touch-x",
    )
    monkeypatch.setenv(
        "WP_HUB_RELEASE_REMOTE_EXECUTABLE_SHA256",
        "a" * 64,
    )

    with pytest.raises(
        ValueError,
        match="wp_hub_release_ssh_configuration_invalid",
    ):
        module._configuration()


def test_runner_environment_carries_exact_release_bridge_seams():
    root = Path(__file__).resolve().parents[3]
    compose = yaml.safe_load(
        (root / "docker-compose.yml").read_text(encoding="utf-8")
    )
    runner_environment = compose["x-runner-environment"]

    assert {
        "MINDSCAPE_RUNTIME_RESOURCE_PROBE",
        "MINDSCAPE_RUNTIME_RESOURCE_PROBE_SHA256",
        "MINDSCAPE_WP_HUB_RELEASE_FACADE",
        "MINDSCAPE_WP_HUB_RELEASE_FACADE_SHA256",
        "WP_HUB_RELEASE_SSH_HOST",
        "WP_HUB_RELEASE_SSH_PORT",
        "WP_HUB_RELEASE_SSH_USER",
        "WP_HUB_RELEASE_SSH_IDENTITY_FILE",
        "WP_HUB_RELEASE_SSH_IDENTITY_SHA256",
        "WP_HUB_RELEASE_SSH_KNOWN_HOSTS_FILE",
        "WP_HUB_RELEASE_SSH_KNOWN_HOSTS_SHA256",
        "WP_HUB_RELEASE_REMOTE_EXECUTABLE",
        "WP_HUB_RELEASE_REMOTE_EXECUTABLE_SHA256",
    }.issubset(runner_environment)
    runner_volumes = compose["x-runner-volumes"]
    assert any(
        "/run/wp-hub-release/id:ro" in volume
        for volume in runner_volumes
    )
    assert any(
        "/run/wp-hub-release/known_hosts:ro" in volume
        for volume in runner_volumes
    )
