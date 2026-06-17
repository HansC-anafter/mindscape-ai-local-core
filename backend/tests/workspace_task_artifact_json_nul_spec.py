from pathlib import Path

from backend.app.services.json_safety import json_value_without_nul
from backend.app.services.stores.postgres_base import PostgresStoreBase


def test_artifact_progress_parser_normalizes_json_nul_without_dropping_fields():
    raw = (
        '{"progress":{"message":"bad\\u0000text","percent":50},'
        '"metadata":{"note":"keep\\u0000position"}}'
    )

    parsed = json_value_without_nul(raw)

    assert parsed == {
        "progress": {"message": "bad\ufffdtext", "percent": 50},
        "metadata": {"note": "keep\ufffdposition"},
    }


def test_artifact_progress_parser_preserves_literal_backslash_u0000_text():
    raw = '{"progress":{"message":"literal \\\\u0000 text"}}'

    parsed = json_value_without_nul(raw)

    assert parsed == {"progress": {"message": "literal \\u0000 text"}}


def test_progress_snapshot_queries_do_not_cast_artifact_content_to_jsonb():
    source = (
        Path(__file__).resolve().parents[1]
        / "app/routes/core/workspace/tasks_core/progress_snapshot.py"
    ).read_text(encoding="utf-8")

    assert "content::jsonb" not in source
    assert "json_value_without_nul" in source


def test_postgres_json_serialization_normalizes_real_nul_codepoints():
    store = object.__new__(PostgresStoreBase)

    serialized = store.serialize_json(
        {"text": "bad\x00text", "nested": [{"key\x00": "value\x00"}]}
    )

    assert "\\u0000" not in serialized
    assert store.deserialize_json(serialized) == {
        "text": "bad\ufffdtext",
        "nested": [{"key\ufffd": "value\ufffd"}],
    }
