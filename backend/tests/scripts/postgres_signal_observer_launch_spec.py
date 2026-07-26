from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from scripts.maintenance import postgres_signal_observer_launch as launcher


ARTIFACT_SHA256 = "a" * 64
SOURCE_COMMIT = "b" * 40
IMAGE_DIGEST = "sha256:" + "c" * 64


def _terminal_receipt(path: Path) -> Path:
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    path.write_text(
        json.dumps(
            {
                "phase": "terminal",
                "gate_pass": True,
                "mutation_permit": True,
                "failures": [],
                "artifact_sha256": ARTIFACT_SHA256,
                "checks": {
                    "incident_decision": {
                        "allowed": True,
                        "reason": "incident_diagnostic_permit",
                        "details": {
                            "expires_at": expires_at,
                            "source_commit": SOURCE_COMMIT,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_launcher_uses_no_deps_after_exact_terminal_receipt(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    calls = []

    def _run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", _run)

    result = launcher.main(
        [
            "--terminal-receipt",
            str(_terminal_receipt(tmp_path / "terminal.json")),
            "--artifact-sha256",
            ARTIFACT_SHA256,
            "--source-commit",
            SOURCE_COMMIT,
            "--image-digest",
            IMAGE_DIGEST,
        ]
    )

    assert result == 0
    command, kwargs = calls[0]
    assert command[-4:] == [
        "up",
        "-d",
        "--no-deps",
        "postgres-signal-observer",
    ]
    assert command.count("--no-deps") == 1
    assert kwargs["env"]["POSTGRES_SIGNAL_OBSERVER_SOURCE_COMMIT"] == SOURCE_COMMIT
    assert json.loads(capsys.readouterr().out)["dependency_reconciliation"] is False


def test_launcher_rejects_source_commit_not_bound_to_permit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("docker must not run")
        ),
    )

    try:
        launcher.main(
            [
                "--terminal-receipt",
                str(_terminal_receipt(tmp_path / "terminal.json")),
                "--artifact-sha256",
                ARTIFACT_SHA256,
                "--source-commit",
                "d" * 40,
                "--image-digest",
                IMAGE_DIGEST,
            ]
        )
    except SystemExit as exc:
        assert str(exc) == "observer_terminal_receipt_permit_mismatch"
    else:
        raise AssertionError("source mismatch must fail closed")
