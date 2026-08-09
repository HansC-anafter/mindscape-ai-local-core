from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHELL_FACADE = REPO_ROOT / "scripts/runtime_secrets/runtime_secrets.sh"
COMPOSE_FACADE = REPO_ROOT / "scripts/compose.sh"


def _run_shell_bootstrap(project_root: Path) -> subprocess.CompletedProcess[str]:
    command = (
        'source "$1"; '
        'mindscape_initialize_runtime_secrets "$2"; '
        'printf "%s|%s" "$MINDSCAPE_RUNTIME_SECRET_STATE" '
        '"$MINDSCAPE_RUNTIME_SECRET_BACKEND"'
    )
    return subprocess.run(
        ["bash", "-c", command, "bootstrap-test", str(SHELL_FACADE), str(project_root)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "MINDSCAPE_RUNTIME_SECRET_ROOT": ""},
    )


def test_unix_bootstrap_imports_legacy_once_without_rewriting_env(tmp_path):
    project_root = tmp_path / "local-core"
    project_root.mkdir()
    env_file = project_root / ".env"
    original_env = "OPENAI_API_KEY=\nPOSTGRES_VECTOR_RUNTIME_PASSWORD='legacy-p@ss'\n"
    env_file.write_text(original_env, encoding="utf-8")

    first = _run_shell_bootstrap(project_root)
    secret_file = project_root / "data/secrets/postgres_vector_runtime_password"

    assert first.stdout == "imported|file"
    assert "legacy-p@ss" not in first.stdout + first.stderr
    assert secret_file.read_text(encoding="utf-8") == "legacy-p@ss"
    assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(secret_file.parent.stat().st_mode) == 0o700
    assert env_file.read_text(encoding="utf-8") == original_env

    second = _run_shell_bootstrap(project_root)
    assert second.stdout == "existing|file"
    assert secret_file.read_text(encoding="utf-8") == "legacy-p@ss"


def test_unix_bootstrap_generates_secret_without_logging_it(tmp_path):
    project_root = tmp_path / "local-core"
    project_root.mkdir()

    result = _run_shell_bootstrap(project_root)
    secret_file = project_root / "data/secrets/postgres_vector_runtime_password"
    secret = secret_file.read_text(encoding="utf-8")

    assert result.stdout == "created|file"
    assert len(secret) == 64
    assert secret not in result.stdout + result.stderr


def test_unix_bootstrap_rejects_multiline_managed_secret(tmp_path):
    project_root = tmp_path / "local-core"
    secret_root = project_root / "data/secrets"
    secret_root.mkdir(parents=True, mode=0o700)
    secret_root.chmod(0o700)
    secret_file = secret_root / "postgres_vector_runtime_password"
    secret_file.write_text("first-line\nsecond-line", encoding="utf-8")
    secret_file.chmod(0o600)

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; mindscape_initialize_runtime_secrets "$2"',
            "bootstrap-test",
            str(SHELL_FACADE),
            str(project_root),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "MINDSCAPE_RUNTIME_SECRET_ROOT": ""},
    )

    assert result.returncode != 0
    assert "exactly one line" in result.stderr
    assert "first-line" not in result.stdout + result.stderr


def test_unix_compose_facade_bootstraps_then_forwards_arguments(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_args = tmp_path / "docker-args"
    fake_docker = bin_dir / "docker"
    fake_docker.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$FAKE_DOCKER_ARGS\"\n",
        encoding="utf-8",
    )
    fake_docker.chmod(fake_docker.stat().st_mode | stat.S_IXUSR)
    secret_root = tmp_path / "secrets"

    result = subprocess.run(
        ["bash", str(COMPOSE_FACADE), "--profile", "control-plane", "config"],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_DOCKER_ARGS": str(docker_args),
            "MINDSCAPE_RUNTIME_SECRET_ROOT": str(secret_root),
            "MINDSCAPE_RUNTIME_ENV_FILE": str(tmp_path / "missing.env"),
        },
    )

    assert docker_args.read_text(encoding="utf-8").splitlines() == [
        "compose",
        "--profile",
        "control-plane",
        "config",
    ]
    secret = (secret_root / "postgres_vector_runtime_password").read_text(
        encoding="utf-8"
    )
    assert secret
    assert secret not in result.stdout + result.stderr


def test_windows_adapter_uses_current_user_dpapi_and_no_plaintext_store():
    facade = (REPO_ROOT / "scripts/runtime_secrets/RuntimeSecrets.psm1").read_text(
        encoding="utf-8"
    )
    adapter = (REPO_ROOT / "scripts/runtime_secrets/DpapiSecretStore.psm1").read_text(
        encoding="utf-8"
    )

    assert "DataProtectionScope]::CurrentUser" in adapter
    assert "DataProtectionScope]::LocalMachine" not in adapter
    assert '"System.Security"' in adapter
    assert '"System.Security.Cryptography.ProtectedData"' in adapter
    assert "Add-Type -AssemblyName $assemblyName -ErrorAction Stop" in adapter
    assert adapter.count("Import-MindscapeDpapiAssembly") == 3
    assert "postgres_vector_runtime_password.dpapi" in facade
    assert "WriteAllText($Path, $encoded" in adapter
    assert "WriteAllText($envFile" not in facade
    assert "icacls.exe" in adapter
    assert "Set-MindscapePrivateAcl -Path $Path" in adapter
    assert "Import-MindscapeDpapiAssembly" in adapter
    assert '"System.Security.Cryptography.ProtectedData"' in adapter

    compose_facade = (REPO_ROOT / "scripts/compose.ps1").read_text(encoding="utf-8")
    assert "Import-Module $modulePath" in compose_facade
    assert "Initialize-MindscapeRuntimeSecrets" in compose_facade
    assert "& docker compose @ComposeArguments" in compose_facade


def test_public_windows_update_guides_use_secret_aware_startup_path():
    guide_paths = (
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs/getting-started/installation.md",
        REPO_ROOT / "docs/getting-started/docker.md",
        REPO_ROOT / "docs/getting-started/platform-specific.md",
    )

    for guide_path in guide_paths:
        guide = guide_path.read_text(encoding="utf-8")
        assert "git pull --ff-only" in guide
        assert "scripts\\start.ps1" in guide
        assert "docker compose restart backend" not in guide
