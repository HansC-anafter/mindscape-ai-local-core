from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.maintenance import postgres_signal_observer_drill as drill_facade
from scripts.maintenance.postgres_signal_observer_core import (
    FormalExecutorPythonRuntimeContract,
)


POSTGRES_IMAGE_REF = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE_REF = "mindscape-ai-local-core-backend@sha256:" + "b" * 64


def _contract_tree(tmp_path: Path) -> tuple[FormalExecutorPythonRuntimeContract, Path]:
    canonical = tmp_path / "mindscape-ai-local-core"
    task = tmp_path / "mindscape-ai-local-core-runtime-db-resilience"
    python_entry = canonical / ".venv/bin/python"
    facade = task / "scripts/maintenance/postgres_signal_observer_drill.py"
    (canonical / ".git").mkdir(parents=True)
    python_entry.parent.mkdir(parents=True)
    python_entry.write_bytes(b"canonical-python-runtime")
    python_entry.chmod(0o755)
    facade.parent.mkdir(parents=True)
    facade.write_text("# source-owned facade\n", encoding="utf-8")
    return (
        FormalExecutorPythonRuntimeContract(
            repo_root=task,
            actual_executable=python_entry,
            runtime_prefix=canonical / ".venv",
        ),
        python_entry,
    )


def test_runtime_contract_builds_one_exact_shell_free_facade_argv(tmp_path: Path) -> None:
    contract, python_entry = _contract_tree(tmp_path)

    argv = contract.facade_argv(("--print-bootstrap-spec",))
    spec = contract.redacted_spec()

    assert argv == (
        str(python_entry),
        str(
            tmp_path
            / "mindscape-ai-local-core-runtime-db-resilience"
            / "scripts/maintenance/postgres_signal_observer_drill.py"
        ),
        "--print-bootstrap-spec",
    )
    assert spec["contract"] == "canonical_local_core_venv_python_v1"
    assert spec["python_entry_path"] == str(python_entry)
    assert spec["python_entry_executable"] is True
    assert spec["path_search"] is False
    assert spec["host_fallback"] is False
    assert spec["shell"] is False
    assert spec["second_launcher"] is False
    assert len(spec["python_entry_sha256"]) == 64
    assert len(spec["facade_sha256"]) == 64


@pytest.mark.parametrize(
    ("field", "failure"),
    [
        ("actual_executable", "formal_executor_python_runtime_identity_mismatch"),
        ("runtime_prefix", "formal_executor_python_prefix_identity_mismatch"),
    ],
)
def test_runtime_contract_rejects_identity_drift(
    tmp_path: Path,
    field: str,
    failure: str,
) -> None:
    contract, _python_entry = _contract_tree(tmp_path)
    values = {
        "repo_root": contract.repo_root,
        "actual_executable": contract.actual_executable,
        "runtime_prefix": contract.runtime_prefix,
    }
    values[field] = tmp_path / "unexpected-runtime"

    with pytest.raises(ValueError, match=failure):
        FormalExecutorPythonRuntimeContract(**values).validate()


def test_runtime_contract_rejects_missing_or_nonexecutable_entry(tmp_path: Path) -> None:
    contract, python_entry = _contract_tree(tmp_path)
    python_entry.chmod(0o644)

    with pytest.raises(
        ValueError,
        match="formal_executor_python_runtime_not_executable",
    ):
        contract.validate()

    python_entry.unlink()
    with pytest.raises(ValueError, match="formal_executor_python_runtime_unavailable"):
        contract.validate()


def test_runtime_contract_fails_before_artifact_or_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RejectedRuntime:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def validate(self) -> None:
            raise ValueError("formal_executor_python_runtime_identity_mismatch")

    monkeypatch.setattr(drill_facade, "FormalExecutorPythonRuntimeContract", RejectedRuntime)
    monkeypatch.setattr(
        drill_facade,
        "canonical_observer_artifact_sha256",
        lambda _root: (_ for _ in ()).throw(AssertionError("artifact must not run")),
    )

    with pytest.raises(
        SystemExit,
        match="formal_executor_python_runtime_identity_mismatch",
    ):
        drill_facade.main(
            [
                "--print-client-spec",
                "--drill-suffix",
                "20260718T115447Z",
                "--postgres-drill-image-ref",
                POSTGRES_IMAGE_REF,
                "--observer-backend-image-ref",
                OBSERVER_IMAGE_REF,
                "--database-user",
                "mindscape",
                "--database-name",
                "mindscape_core",
            ]
        )


def test_facade_receipt_exposes_exact_runtime_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = drill_facade.main(
        [
            "--print-client-spec",
            "--drill-suffix",
            "20260718T115447Z",
            "--postgres-drill-image-ref",
            POSTGRES_IMAGE_REF,
            "--observer-backend-image-ref",
            OBSERVER_IMAGE_REF,
            "--database-user",
            "mindscape",
            "--database-name",
            "mindscape_core",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    runtime = payload["formal_executor_python_runtime"]
    assert runtime["python_entry_path"] == os.path.abspath(os.sys.executable)
    assert runtime["runtime_prefix"] == os.path.abspath(os.sys.prefix)
    assert runtime["path_search"] is False
    assert runtime["host_fallback"] is False


def test_runtime_owner_has_no_search_fallback_or_second_launcher() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runtime_source = (
        repo_root
        / "scripts/maintenance/postgres_signal_observer_core/drill_runtime.py"
    ).read_text(encoding="utf-8")
    facade_source = (
        repo_root / "scripts/maintenance/postgres_signal_observer_drill.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("shutil.which", "command -v", "glob(", "shell=True"):
        assert forbidden not in runtime_source
    assert runtime_source.count("class FormalExecutorPythonRuntimeContract") == 1
    assert facade_source.count("FormalExecutorPythonRuntimeContract(") == 1
