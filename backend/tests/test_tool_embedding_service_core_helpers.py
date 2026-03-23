from pathlib import Path
from types import SimpleNamespace

from backend.app.services.tool_embedding_service_core.manifest_context import (
    get_capability_manifest_context,
)
from backend.app.services.tool_embedding_service_core.model_selection import (
    discover_embed_models,
    get_current_embedding_model,
)
from backend.app.services.tool_embedding_service_core.types import ToolMatch
from backend.app.services.tool_embedding_service_core.utils import (
    build_embed_text,
    filter_mapping_rows_by_score,
    fuse_ranked_tool_matches,
    tuple_row_to_tool_match,
    vector_to_pg_literal,
)


def test_build_embed_text_appends_capability_context():
    assert build_embed_text("Tool", "Description") == "Tool: Description"
    assert (
        build_embed_text("Tool", "Description", capability_context="Chinese metadata")
        == "Tool: Description. Chinese metadata"
    )


def test_vector_to_pg_literal_serializes_embedding_values():
    assert vector_to_pg_literal([0.1, 0.2, 0.3]) == "[0.1,0.2,0.3]"


def test_filter_mapping_rows_by_score_builds_tool_matches():
    rows = [
        {
            "tool_id": "tool.keep",
            "display_name": "Keep",
            "description": "Description",
            "category": "utility",
            "capability_code": "tool",
            "similarity": 0.81,
        },
        {
            "tool_id": "tool.drop",
            "display_name": "Drop",
            "description": "Description",
            "category": "utility",
            "capability_code": "tool",
            "similarity": 0.29,
        },
    ]

    matches = filter_mapping_rows_by_score(rows, min_score=0.3)

    assert [match.tool_id for match in matches] == ["tool.keep"]
    assert matches[0].similarity == 0.81


def test_tuple_row_to_tool_match_accepts_explicit_similarity():
    match = tuple_row_to_tool_match(
        ("playbook.demo", "Demo", "Description", "playbook", "demo", 0.2),
        similarity=1.0,
    )

    assert match == ToolMatch(
        tool_id="playbook.demo",
        display_name="Demo",
        description="Description",
        category="playbook",
        capability_code="demo",
        similarity=1.0,
    )


def test_fuse_ranked_tool_matches_keeps_bm25_only_hits():
    per_model_results = [
        [
            ToolMatch("tool.alpha", "Alpha", "Vector", "tool", "alpha", 0.8),
            ToolMatch("tool.beta", "Beta", "Vector", "tool", "beta", 0.4),
        ]
    ]
    bm25_results = [
        ToolMatch("tool.lexical", "Lexical", "BM25", "tool", "lexical", 0.0),
        ToolMatch("tool.alpha", "Alpha", "BM25", "tool", "alpha", 0.0),
    ]

    matches = fuse_ranked_tool_matches(
        per_model_results=per_model_results,
        bm25_results=bm25_results,
        top_k=3,
        min_score=0.3,
        rrf_k=60,
    )

    assert [match.tool_id for match in matches] == [
        "tool.alpha",
        "tool.lexical",
        "tool.beta",
    ]
    assert matches[1].similarity > 0


def test_get_capability_manifest_context_reads_and_caches(tmp_path: Path):
    services_dir = tmp_path / "services"
    manifest_path = services_dir / "capabilities" / "demo" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        "display_name_zh: 示範工具\n"
        "description: 這是一段中文描述，用來驗證快取與跨語系補充。\n",
        encoding="utf-8",
    )
    cache: dict[str, str | None] = {}

    first = get_capability_manifest_context(
        cache=cache,
        capability_code="demo",
        services_dir=services_dir,
    )
    manifest_path.write_text(
        "display_name_zh: 已修改\n"
        "description: changed\n",
        encoding="utf-8",
    )
    second = get_capability_manifest_context(
        cache=cache,
        capability_code="demo",
        services_dir=services_dir,
    )

    assert first == "示範工具 這是一段中文描述，用來驗證快取與跨語系補充。"
    assert second == first


def test_discover_embed_models_filters_and_deduplicates():
    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "models": [
                    {"name": "bge-m3:latest"},
                    {"name": "bge-m3:latest"},
                    {"name": "llama3:8b"},
                    {"name": "nomic-embed-text:latest"},
                ]
            }

    models = discover_embed_models(
        requests_get=lambda url, timeout: _Response(),
        env_host="http://ollama:11434",
    )

    assert models == ["bge-m3", "nomic-embed-text"]


def test_get_current_embedding_model_prefers_frontend_setting():
    class _Store:
        def get_setting(self, key):
            if key == "ollama_embed_model":
                return SimpleNamespace(value="bge-m3")
            return None

    model = get_current_embedding_model(
        system_settings_store_cls=_Store,
        requests_get=lambda url, timeout: None,
        environ={},
    )

    assert model == "bge-m3"


def test_get_current_embedding_model_uses_env_override_when_ollama_is_available():
    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {"models": [{"name": "bge-m3:latest"}]}

    model = get_current_embedding_model(
        system_settings_store_cls=lambda: SimpleNamespace(get_setting=lambda key: None),
        requests_get=lambda url, timeout: _Response(),
        environ={"OLLAMA_EMBED_MODEL": "custom-embed", "OLLAMA_HOST": "http://ollama"},
    )

    assert model == "custom-embed"
