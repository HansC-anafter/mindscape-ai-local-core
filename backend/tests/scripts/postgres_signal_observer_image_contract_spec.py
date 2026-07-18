from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.maintenance import postgres_signal_observer_drill as drill_facade
from scripts.maintenance.postgres_signal_observer_core import (
    OBSERVER_BACKEND_IMAGE_ROLE,
    POSTGRES_DRILL_IMAGE_ROLE,
    DisposableDrillBootstrapConfig,
    DisposableDrillClientConfig,
    DisposableDrillImageContract,
    DisposableDrillObserverConfig,
    DisposableDrillSignalConfig,
    canonical_observer_artifact_sha256,
    launch_disposable_drill_observer,
    validate_drill_image_ref,
)


DRILL_SUFFIX = "20260718T103518Z"
POSTGRES_IMAGE_REF = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE_REF = "mindscape-ai-local-core-backend@sha256:" + "b" * 64


def _image_args() -> list[str]:
    return [
        "--postgres-drill-image-ref",
        POSTGRES_IMAGE_REF,
        "--observer-backend-image-ref",
        OBSERVER_IMAGE_REF,
    ]


def test_role_contract_persists_two_exact_owners_and_binding_hashes() -> None:
    contract = DisposableDrillImageContract(
        postgres_image_ref=POSTGRES_IMAGE_REF,
        observer_image_ref=OBSERVER_IMAGE_REF,
    )

    spec = contract.redacted_spec()

    assert set(spec["roles"]) == {
        POSTGRES_DRILL_IMAGE_ROLE,
        OBSERVER_BACKEND_IMAGE_ROLE,
    }
    assert spec["legacy_image_ref_accepted"] is False
    for role, expected_ref in {
        POSTGRES_DRILL_IMAGE_ROLE: POSTGRES_IMAGE_REF,
        OBSERVER_BACKEND_IMAGE_ROLE: OBSERVER_IMAGE_REF,
    }.items():
        role_spec = spec["roles"][role]
        assert role_spec["image_ref"] == expected_ref
        assert role_spec["image_digest"] == (
            "sha256:" + expected_ref.rpartition("@sha256:")[2]
        )
        assert re.fullmatch(
            r"[0-9a-f]{64}",
            role_spec["facade_binding_argv_sha256"],
        )


@pytest.mark.parametrize(
    ("image_ref", "role", "failure"),
    [
        (
            OBSERVER_IMAGE_REF,
            POSTGRES_DRILL_IMAGE_ROLE,
            "postgres_drill_pg16_image_owner_mismatch",
        ),
        (
            POSTGRES_IMAGE_REF,
            OBSERVER_BACKEND_IMAGE_ROLE,
            "observer_backend_image_owner_mismatch",
        ),
        (
            "mindscape-ai-local-core-postgres:pg16:latest",
            POSTGRES_DRILL_IMAGE_ROLE,
            "postgres_drill_pg16_image_ref_invalid",
        ),
        (
            "mindscape-ai-local-core-postgres:pg16@sha256:" + "A" * 64,
            POSTGRES_DRILL_IMAGE_ROLE,
            "postgres_drill_pg16_image_ref_invalid",
        ),
    ],
)
def test_role_validator_rejects_wrong_unpinned_or_uppercase_digest(
    image_ref: str,
    role: str,
    failure: str,
) -> None:
    with pytest.raises(ValueError, match=failure):
        validate_drill_image_ref(image_ref, role=role)


@pytest.mark.parametrize("missing_option", ["postgres", "observer"])
def test_facade_requires_both_role_specific_image_arguments(
    missing_option: str,
) -> None:
    argv = ["--print-client-spec", "--drill-suffix", DRILL_SUFFIX]
    if missing_option != "postgres":
        argv.extend(["--postgres-drill-image-ref", POSTGRES_IMAGE_REF])
    if missing_option != "observer":
        argv.extend(["--observer-backend-image-ref", OBSERVER_IMAGE_REF])
    argv.extend(["--database-user", "mindscape", "--database-name", "mindscape"])

    with pytest.raises(SystemExit):
        drill_facade.main(argv)


def test_facade_rejects_legacy_generic_image_argument() -> None:
    with pytest.raises(SystemExit):
        drill_facade.main(
            [
                "--print-client-spec",
                "--drill-suffix",
                DRILL_SUFFIX,
                *_image_args(),
                "--image-ref",
                POSTGRES_IMAGE_REF,
                "--database-user",
                "mindscape",
                "--database-name",
                "mindscape",
            ]
        )


def test_cross_role_contract_fails_before_artifact_or_runtime_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        drill_facade,
        "canonical_observer_artifact_sha256",
        lambda _root: (_ for _ in ()).throw(
            AssertionError("artifact read must follow role validation")
        ),
    )

    with pytest.raises(SystemExit, match="postgres_drill_pg16_image_owner_mismatch"):
        drill_facade.main(
            [
                "--print-client-spec",
                "--drill-suffix",
                DRILL_SUFFIX,
                "--postgres-drill-image-ref",
                OBSERVER_IMAGE_REF,
                "--observer-backend-image-ref",
                POSTGRES_IMAGE_REF,
                "--database-user",
                "mindscape",
                "--database-name",
                "mindscape",
            ]
        )


def test_postgres_role_consumers_reject_backend_image() -> None:
    consumers = [
        DisposableDrillBootstrapConfig(
            drill_suffix=DRILL_SUFFIX,
            temp_root=Path(
                f"/private/tmp/mindscape-postgres-signal-drill-{DRILL_SUFFIX}"
            ),
            postgres_image_ref=OBSERVER_IMAGE_REF,
        ),
        DisposableDrillClientConfig(
            container_name="runtime-db-observer-drill-client-20260718t103518z",
            network_name="runtime-db-observer-drill-20260718t103518z",
            postgres_image_ref=OBSERVER_IMAGE_REF,
            pgbouncer_host="runtime-db-observer-drill-pgbouncer-20260718t103518z",
            pgbouncer_port=6432,
            database_user="mindscape",
            database_name="mindscape",
        ),
        DisposableDrillSignalConfig(
            drill_suffix=DRILL_SUFFIX,
            postgres_image_ref=OBSERVER_IMAGE_REF,
            target_postgres_pid=96,
        ),
    ]

    for config in consumers:
        with pytest.raises(ValueError, match="postgres_drill_pg16_image_owner_mismatch"):
            config.validate()


def test_observer_role_consumer_rejects_postgres_image(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    config = DisposableDrillObserverConfig(
        container_name="runtime-db-observer-drill-observer-20260718t103518z",
        pgbouncer_container_name=(
            "runtime-db-observer-drill-pgbouncer-20260718t103518z"
        ),
        observer_image_ref=POSTGRES_IMAGE_REF,
        journal_host_root=journal_root,
        repo_root=repo_root,
        artifact_sha256=canonical_observer_artifact_sha256(repo_root),
        source_commit="0123456789abcdef",
    )

    with pytest.raises(ValueError, match="observer_backend_image_owner_mismatch"):
        config.validate()


def test_single_facade_modes_select_only_their_owned_image(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    temp_root = Path(f"/private/tmp/mindscape-postgres-signal-drill-{DRILL_SUFFIX}")
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    cases = [
        (
            [
                "--print-bootstrap-spec",
                "--drill-suffix",
                DRILL_SUFFIX,
                "--temp-root",
                str(temp_root),
                *_image_args(),
            ],
            POSTGRES_DRILL_IMAGE_ROLE,
            POSTGRES_IMAGE_REF,
        ),
        (
            [
                "--print-client-spec",
                "--drill-suffix",
                DRILL_SUFFIX,
                *_image_args(),
                "--database-user",
                "mindscape",
                "--database-name",
                "mindscape",
            ],
            POSTGRES_DRILL_IMAGE_ROLE,
            POSTGRES_IMAGE_REF,
        ),
        (
            [
                "--print-signal-spec",
                "--drill-suffix",
                DRILL_SUFFIX,
                *_image_args(),
                "--target-postgres-pid",
                "96",
            ],
            POSTGRES_DRILL_IMAGE_ROLE,
            POSTGRES_IMAGE_REF,
        ),
        (
            [
                "--print-observer-spec",
                "--drill-suffix",
                DRILL_SUFFIX,
                "--journal-root",
                str(journal_root),
                *_image_args(),
                "--source-commit",
                "0123456789abcdef",
            ],
            OBSERVER_BACKEND_IMAGE_ROLE,
            OBSERVER_IMAGE_REF,
        ),
    ]

    for argv, expected_role, expected_ref in cases:
        assert drill_facade.main(argv) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["selected_image_role"] == expected_role
        assert payload["image_role"] == expected_role
        assert payload["image_ref"] == expected_ref
        assert set(payload["image_contract"]["roles"]) == {
            POSTGRES_DRILL_IMAGE_ROLE,
            OBSERVER_BACKEND_IMAGE_ROLE,
        }
        selected_argv_sha256 = payload.get("argv_sha256") or payload.get(
            "postgres_argv_sha256"
        )
        assert re.fullmatch(r"[0-9a-f]{64}", selected_argv_sha256)


def test_observer_failure_receipt_keeps_observer_role_spec(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    config = DisposableDrillObserverConfig(
        container_name="runtime-db-observer-drill-observer-20260718t103518z",
        pgbouncer_container_name=(
            "runtime-db-observer-drill-pgbouncer-20260718t103518z"
        ),
        observer_image_ref=OBSERVER_IMAGE_REF,
        journal_host_root=journal_root,
        repo_root=repo_root,
        artifact_sha256=canonical_observer_artifact_sha256(repo_root),
        source_commit="0123456789abcdef",
    )

    def fake_run(argv, **_kwargs):
        if argv[:3] == ["docker", "run", "-d"]:
            return SimpleNamespace(returncode=127, stdout=b"opaque", stderr=b"hidden")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    receipt = launch_disposable_drill_observer(
        config,
        environment={"PGBOUNCER_ADMIN_URL": "postgresql://fixture-only"},
        run=fake_run,
    )
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["first_failure"] == "disposable_drill_observer_launch_failed"
    assert receipt["spec"]["image_role"] == OBSERVER_BACKEND_IMAGE_ROLE
    assert receipt["spec"]["image_ref"] == OBSERVER_IMAGE_REF
    assert receipt["spec"]["image_digest"] == "sha256:" + "b" * 64
    assert re.fullmatch(r"[0-9a-f]{64}", receipt["spec"]["argv_sha256"])
    assert "opaque" not in serialized
    assert "hidden" not in serialized


def test_role_contract_keeps_one_facade_and_no_compose_or_launcher_side_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    maintenance_root = repo_root / "scripts/maintenance"
    parser_hits = []
    observer_launcher_hits = []
    for path in maintenance_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(repo_root).as_posix()
        if 'add_argument("--postgres-drill-image-ref"' in source:
            parser_hits.append(relative)
        if re.search(r"def\s+launch_disposable_drill_observer\(", source):
            observer_launcher_hits.append(relative)

    facade_source = (
        repo_root / "scripts/maintenance/postgres_signal_observer_drill.py"
    ).read_text(encoding="utf-8")
    compose_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (repo_root / "docker").rglob("*.yml")
    )
    assert parser_hits == ["scripts/maintenance/postgres_signal_observer_drill.py"]
    assert observer_launcher_hits == [
        "scripts/maintenance/postgres_signal_observer_core/drill_observer.py"
    ]
    assert 'add_argument("--image-ref"' not in facade_source
    assert "--postgres-drill-image-ref" not in compose_source
    assert "--observer-backend-image-ref" not in compose_source
    assert "shell=True" not in facade_source
    assert "fallback" not in facade_source.lower()
