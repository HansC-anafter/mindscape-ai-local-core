from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import pytest

from scripts.maintenance import postgres_signal_observer_drill as drill_facade
from scripts.maintenance.postgres_signal_observer_core import (
    DisposableDrillBootstrapConfig,
    DisposableDrillObserverConfig,
    DisposableDrillObserverEnvironment,
    canonical_observer_artifact_sha256,
    launch_disposable_drill_observer,
    serialize_disposable_pgbouncer_config,
    serialize_disposable_pgbouncer_userlist,
    serialize_postgres_bootstrap_environment,
)


POSTGRES_IMAGE_REF = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE_REF = "mindscape-ai-local-core-backend@sha256:" + "b" * 64
DRILL_SUFFIX = "20260718T121226Z"
TEMP_ROOT = Path(f"/private/tmp/mindscape-postgres-signal-drill-{DRILL_SUFFIX}")
ASSIGNMENTS = {
    "POSTGRES_USER": "mindscape",
    "POSTGRES_PASSWORD": "fixture@pass:/+%-value",
    "POSTGRES_DB": "mindscape_core",
}


@pytest.fixture
def bootstrap_config() -> DisposableDrillBootstrapConfig:
    shutil.rmtree(TEMP_ROOT, ignore_errors=True)
    TEMP_ROOT.mkdir(mode=0o700)
    config = DisposableDrillBootstrapConfig(
        drill_suffix=DRILL_SUFFIX,
        temp_root=TEMP_ROOT,
        postgres_image_ref=POSTGRES_IMAGE_REF,
    )
    payloads = {
        config.postgres_environment_path: serialize_postgres_bootstrap_environment(
            ASSIGNMENTS
        ),
        config.pgbouncer_config_path: serialize_disposable_pgbouncer_config(
            ASSIGNMENTS
        ),
        config.pgbouncer_userlist_path: serialize_disposable_pgbouncer_userlist(
            ASSIGNMENTS
        ),
    }
    for path, payload in payloads.items():
        path.write_bytes(payload)
        path.chmod(0o600)
    try:
        yield config
    finally:
        shutil.rmtree(TEMP_ROOT, ignore_errors=True)


def _observer_config(
    bootstrap: DisposableDrillBootstrapConfig,
    tmp_path: Path,
) -> DisposableDrillObserverConfig:
    repo_root = Path(__file__).resolve().parents[3]
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    return DisposableDrillObserverConfig(
        container_name=bootstrap.observer_container_name,
        pgbouncer_container_name=bootstrap.pgbouncer_container_name,
        observer_image_ref=OBSERVER_IMAGE_REF,
        journal_host_root=journal_root,
        repo_root=repo_root,
        artifact_sha256=canonical_observer_artifact_sha256(repo_root),
        source_commit="0123456789abcdef",
    )


def test_derives_exact_isolated_admin_url_and_redacts_receipt_identity(
    bootstrap_config: DisposableDrillBootstrapConfig,
) -> None:
    contract = DisposableDrillObserverEnvironment.from_isolated_preconditions(
        bootstrap_config,
        base_environment={"PATH": "/usr/local/bin:/usr/bin"},
    )
    child = contract.subprocess_environment()
    parsed = urlsplit(child["PGBOUNCER_ADMIN_URL"])
    spec = contract.redacted_spec()
    serialized = json.dumps(spec, sort_keys=True)

    assert parsed.scheme == "postgresql"
    assert parsed.hostname == "127.0.0.1"
    assert parsed.port == 6432
    assert parsed.path == "/pgbouncer"
    assert unquote(parsed.username or "") == ASSIGNMENTS["POSTGRES_USER"]
    assert unquote(parsed.password or "") == ASSIGNMENTS["POSTGRES_PASSWORD"]
    assert child["PATH"] == "/usr/local/bin:/usr/bin"
    assert spec["environment_key_present"] is True
    assert spec["network_contract"] == "shared_pgbouncer_network_namespace_v1"
    assert spec["host_environment_value_read"] is False
    assert spec["host_environment_value_inherited"] is False
    assert spec["url_or_credential_disclosed"] is False
    assert child["PGBOUNCER_ADMIN_URL"] not in serialized
    assert ASSIGNMENTS["POSTGRES_PASSWORD"] not in serialized
    assert "postgresql://" not in serialized


def test_host_admin_url_is_rejected_without_reading_or_inheriting_its_value(
    bootstrap_config: DisposableDrillBootstrapConfig,
) -> None:
    with pytest.raises(
        RuntimeError,
        match="drill_observer_host_pgbouncer_admin_url_environment_forbidden",
    ):
        DisposableDrillObserverEnvironment.from_isolated_preconditions(
            bootstrap_config,
            base_environment={
                "PATH": "/usr/bin",
                "PGBOUNCER_ADMIN_URL": "postgresql://host-secret",
            },
        )


@pytest.mark.parametrize(
    ("target", "failure"),
    [
        ("missing_config", "drill_observer_pgbouncer_config_unavailable"),
        ("config_mode", "drill_observer_pgbouncer_config_contract_invalid"),
        ("config_drift", "drill_observer_pgbouncer_config_readback_mismatch"),
        ("userlist_drift", "drill_observer_pgbouncer_userlist_readback_mismatch"),
    ],
)
def test_missing_or_drifted_preconditions_fail_before_observer_docker(
    bootstrap_config: DisposableDrillBootstrapConfig,
    target: str,
    failure: str,
) -> None:
    if target == "missing_config":
        bootstrap_config.pgbouncer_config_path.unlink()
    elif target == "config_mode":
        bootstrap_config.pgbouncer_config_path.chmod(0o644)
    elif target == "config_drift":
        bootstrap_config.pgbouncer_config_path.write_bytes(b"[pgbouncer]\n")
        bootstrap_config.pgbouncer_config_path.chmod(0o600)
    else:
        bootstrap_config.pgbouncer_userlist_path.write_bytes(b'"other" "value"\n')
        bootstrap_config.pgbouncer_userlist_path.chmod(0o600)

    with pytest.raises(RuntimeError, match=failure):
        DisposableDrillObserverEnvironment.from_isolated_preconditions(
            bootstrap_config,
            base_environment={"PATH": "/usr/bin"},
        )


def test_launcher_injects_url_only_in_child_environment_and_receipt_is_redacted(
    bootstrap_config: DisposableDrillBootstrapConfig,
    tmp_path: Path,
) -> None:
    contract = DisposableDrillObserverEnvironment.from_isolated_preconditions(
        bootstrap_config,
        base_environment={"PATH": "/usr/local/bin:/usr/bin"},
    )
    config = _observer_config(bootstrap_config, tmp_path)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(argv, **kwargs):
        calls.append((list(argv), kwargs))
        if argv[1:3] == ["run", "-d"]:
            return SimpleNamespace(returncode=125, stdout=b"", stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    receipt = launch_disposable_drill_observer(
        config,
        environment_contract=contract,
        run=run,
    )
    child_url = contract.subprocess_environment()["PGBOUNCER_ADMIN_URL"]
    serialized = json.dumps(receipt, sort_keys=True)

    assert calls[0][1]["env"]["PGBOUNCER_ADMIN_URL"] == child_url
    assert calls[0][1]["shell"] is False
    assert "PGBOUNCER_ADMIN_URL" in calls[0][0]
    assert child_url not in "\0".join(calls[0][0])
    assert child_url not in serialized
    assert ASSIGNMENTS["POSTGRES_PASSWORD"] not in serialized
    assert receipt["first_failure"] == "disposable_drill_observer_launch_failed"
    assert receipt["pgbouncer_admin_environment"]["environment_key_present"] is True
    assert all(
        "PGBOUNCER_ADMIN_URL" not in call[1]["env"] for call in calls[1:]
    )


def test_environment_identity_drift_blocks_before_docker(
    bootstrap_config: DisposableDrillBootstrapConfig,
    tmp_path: Path,
) -> None:
    contract = DisposableDrillObserverEnvironment.from_isolated_preconditions(
        bootstrap_config,
        base_environment={"PATH": "/usr/bin"},
    )
    config = _observer_config(bootstrap_config, tmp_path)
    drifted = DisposableDrillObserverConfig(
        **{
            **config.__dict__,
            "pgbouncer_container_name": "runtime-db-observer-drill-pgbouncer-drift",
        }
    )
    called = False

    def run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("Docker must not run")

    with pytest.raises(
        ValueError,
        match="drill_observer_pgbouncer_environment_identity_mismatch",
    ):
        launch_disposable_drill_observer(
            drifted,
            environment_contract=contract,
            run=run,
        )
    assert called is False


def test_formal_facade_uses_single_precondition_derived_environment_contract(
    bootstrap_config: DisposableDrillBootstrapConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    captured: dict[str, object] = {}
    marker = object()

    def build(**kwargs):
        captured["build"] = kwargs
        return marker

    def execute(config):
        captured["execute"] = config
        return {"validation_passed": True, "secret_value_disclosed": False}

    monkeypatch.setattr(drill_facade, "build_formal_drill_cli_config", build)
    monkeypatch.setattr(drill_facade, "execute_canonical_formal_drill", execute)

    exit_code = drill_facade.main(
        [
            "--execute-formal-drill-sequence",
            "--journal-root",
            str(journal_root),
            "--drill-suffix",
            DRILL_SUFFIX,
            "--postgres-drill-image-ref",
            POSTGRES_IMAGE_REF,
            "--observer-backend-image-ref",
            OBSERVER_IMAGE_REF,
            "--source-commit",
            "0123456789abcdef",
            "--database-user",
            "mindscape",
            "--database-name",
            "mindscape_core",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured["build"]["drill_suffix"] == DRILL_SUFFIX
    assert captured["build"]["temp_root"] == TEMP_ROOT
    assert captured["execute"] is marker
    assert payload["validation_passed"] is True
    assert "postgresql://" not in json.dumps(payload, sort_keys=True)


def test_formal_facade_rejects_caller_owned_temp_root_before_execution(
    bootstrap_config: DisposableDrillBootstrapConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal_root = tmp_path / "journal"
    journal_root.mkdir()

    def unexpected(**_kwargs):
        raise AssertionError("formal sequence construction must remain blocked")

    monkeypatch.setattr(drill_facade, "build_formal_drill_cli_config", unexpected)
    monkeypatch.setattr(drill_facade, "execute_canonical_formal_drill", unexpected)

    with pytest.raises(SystemExit, match="formal_drill_temp_root_caller_owned"):
        drill_facade.main(
            [
                "--execute-formal-drill-sequence",
                "--journal-root",
                str(journal_root),
                "--drill-suffix",
                DRILL_SUFFIX,
                "--temp-root",
                str(bootstrap_config.temp_root),
                "--postgres-drill-image-ref",
                POSTGRES_IMAGE_REF,
                "--observer-backend-image-ref",
                OBSERVER_IMAGE_REF,
                "--source-commit",
                "0123456789abcdef",
                "--database-user",
                "mindscape",
                "--database-name",
                "mindscape_core",
            ]
        )


def test_single_launcher_has_no_host_environment_or_second_provisioning_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    observer_source = (
        repo_root / "scripts/maintenance/postgres_signal_observer_core/drill_observer.py"
    ).read_text(encoding="utf-8")
    facade_source = (
        repo_root / "scripts/maintenance/postgres_signal_observer_drill.py"
    ).read_text(encoding="utf-8")
    formal_cli_source = (
        repo_root
        / "scripts/maintenance/postgres_signal_observer_core/drill_formal_cli.py"
    ).read_text(encoding="utf-8")

    assert "os.environ" not in observer_source
    assert observer_source.count("def launch_disposable_drill_observer(") == 1
    assert formal_cli_source.count(
        "DisposableDrillObserverEnvironment.from_isolated_preconditions("
    ) == 1
    assert "PGBOUNCER_ADMIN_URL=" not in facade_source + formal_cli_source
    assert "shell=True" not in facade_source + formal_cli_source
