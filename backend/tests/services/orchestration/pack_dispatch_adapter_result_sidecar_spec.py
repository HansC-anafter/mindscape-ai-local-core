"""Focused tests for the pack dispatch adapter result sidecar seam."""

from pathlib import Path

from backend.app.services.orchestration.pack_dispatch_adapter import (
    PackDispatchAdapter,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
TARGET = REPO_ROOT / "backend/app/services/orchestration/pack_dispatch_adapter.py"
CORE_DIR = REPO_ROOT / "backend/app/services/orchestration/pack_dispatch_adapter_core"
SPEC = REPO_ROOT / "backend/tests/services/orchestration/pack_dispatch_adapter_result_sidecar_spec.py"


def test_parse_result_builds_sidecar_without_mutating_raw_result(monkeypatch):
    monkeypatch.setattr(
        PackDispatchAdapter,
        "_load_playbook_spec",
        staticmethod(lambda playbook_code: None),
    )
    raw = {"output": "hello world", "steps": [{"id": "s1"}]}

    sidecar = PackDispatchAdapter().parse_result(
        result_data=raw,
        playbook_code="demo.playbook",
    )

    assert sidecar["provenance_schema_version"] == "1.1"
    assert sidecar["playbook_code"] == "demo.playbook"
    assert sidecar["parsed_by"] == "pack_dispatch_adapter_v1"
    assert sidecar["trace_index"] == {"entries": []}
    assert sidecar["output_hash"]
    assert "output_hash" not in raw
    assert "parsed_by" not in raw


def test_parse_result_matches_spec_outputs_from_public_adapter(monkeypatch):
    monkeypatch.setattr(
        PackDispatchAdapter,
        "_load_playbook_spec",
        staticmethod(
            lambda playbook_code: {
                "outputs": {
                    "summary": {
                        "type": "string",
                        "source": "step.summarize.text",
                    },
                    "missing": {
                        "type": "string",
                        "source": "step.nope.text",
                    },
                },
            }
        ),
    )

    sidecar = PackDispatchAdapter().parse_result(
        result_data={"step": {"summarize": {"text": "Done"}}},
        playbook_code="demo.playbook",
    )

    assert sidecar["outputs_matched"]["summary"]["resolved"] is True
    assert sidecar["outputs_matched"]["summary"]["value_present"] is True
    assert sidecar["outputs_matched"]["missing"]["resolved"] is False
    assert sidecar["resolved_outputs"]["summary"] == "Done"


def test_parse_result_dedupes_context_attachments(monkeypatch):
    monkeypatch.setattr(
        PackDispatchAdapter,
        "_load_playbook_spec",
        staticmethod(lambda playbook_code: None),
    )

    sidecar = PackDispatchAdapter().parse_result(
        result_data={
            "context_attachments": [{"ref": "artifact-1"}],
            "metadata": {
                "context_attachments": [{"ref": "artifact-1"}],
            },
            "attachments": [{"filename": "summary.md"}],
        },
        playbook_code="demo.playbook",
    )

    assert sidecar["context_attachments"] == [
        {"ref": "artifact-1"},
        {"filename": "summary.md"},
    ]


def test_parse_result_handles_non_dict_result(monkeypatch):
    def fail_on_spec_load(playbook_code):
        raise AssertionError("non-dict result should not load playbook spec")

    monkeypatch.setattr(
        PackDispatchAdapter,
        "_load_playbook_spec",
        staticmethod(fail_on_spec_load),
    )

    sidecar = PackDispatchAdapter().parse_result(
        result_data="plain output",
        playbook_code="demo.playbook",
    )

    assert sidecar["output_hash"]
    assert "outputs_matched" not in sidecar


def test_private_helper_aliases_remain_available_on_adapter():
    adapter = PackDispatchAdapter()

    assert adapter._resolve_source_path({"a": {"b": 1}}, "a.b") == 1
    assert adapter._legacy_step_output_source("step.make.value") == (
        "step_outputs.make.value"
    )
    assert adapter._resolve_output_value(
        roots=[{"outputs": {"summary": "Done"}}],
        output_name="summary",
        source="",
    ) == "Done"
    assert adapter._has_material_value("value") is True
    assert adapter._first_value({"a": {"b": "x"}}, ["missing", "a.b"]) == "x"
    assert adapter._compute_hash({"a": 1})


def test_pack_dispatch_adapter_files_stay_below_line_gate():
    paths = [TARGET, CORE_DIR / "__init__.py", CORE_DIR / "result_sidecar.py", SPEC]

    for path in paths:
        assert len(path.read_text().splitlines()) <= 500, path


def test_result_sidecar_core_has_no_shared_resource_markers():
    text = "\n".join(path.read_text() for path in CORE_DIR.glob("*.py"))
    markers = [
        "Mindscape" + "Store",
        "session" + "maker",
        "create_" + "engine",
        "Pg" + "Bouncer",
        "create_" + "task",
        "Q" + "ueue(",
        "Th" + "read(",
        "Pro" + "cess(",
        "re" + "dis",
        "poll" + "ing",
        "Event" + "Source",
        "Web" + "Socket",
        "web" + "socket",
        "set" + "Interval",
        "set" + "Timeout",
        "work" + "er",
        "Playbook" + "JsonLoader",
        "Fast" + "API",
        "API" + "Router",
    ]

    assert [marker for marker in markers if marker in text] == []
