import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.runtime_contract_paths import (
    build_validation_pythonpath,
    resolve_capability_runtime_import_roots,
    resolve_runtime_contracts_root,
)
from app.services.tool_rag_refresh import refresh_tool_rag_corpus


def test_build_validation_pythonpath_includes_runtime_root_once(tmp_path: Path):
    local_core_root = tmp_path / "local-core"
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    capability_dir = capabilities_dir / "demo_pack"

    roots = resolve_capability_runtime_import_roots(capability_dir)
    pythonpath = build_validation_pythonpath(local_core_root, capabilities_dir)
    parts = pythonpath.split(":")

    assert roots == [
        local_core_root / "backend",
        local_core_root / "backend" / "app",
        capabilities_dir,
        resolve_runtime_contracts_root(local_core_root),
    ]
    assert parts == [str(local_core_root), *[str(path) for path in roots]]
    assert parts.count(str(resolve_runtime_contracts_root(local_core_root))) == 1


@pytest.mark.asyncio
async def test_refresh_tool_rag_corpus_falls_back_when_ensure_indexed_raises(
    monkeypatch,
):
    events = []

    class FakeToolEmbeddingService:
        async def ensure_table(self):
            events.append("ensure_table")

        async def ensure_indexed(self):
            events.append("ensure_indexed")
            raise RuntimeError("force fallback")

        async def index_all_tools(self):
            events.append("index_all_tools")
            return 7

    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.tool_embedding_service",
        SimpleNamespace(ToolEmbeddingService=FakeToolEmbeddingService),
    )

    tes, indexed_count, mode = await refresh_tool_rag_corpus(
        log_prefix="runtime-contract-test"
    )

    assert isinstance(tes, FakeToolEmbeddingService)
    assert indexed_count == 7
    assert mode == "index_all_tools_fallback"
    assert events == ["ensure_table", "ensure_indexed", "index_all_tools"]
