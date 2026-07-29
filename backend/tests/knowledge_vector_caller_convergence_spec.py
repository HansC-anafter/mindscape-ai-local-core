"""Static guard against reintroducing raw vector DML in product entries."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.vector_search import VectorSearchService


ROOT = Path(__file__).resolve().parents[1]
LEGACY_SERVICE_PATHS = (
    ROOT / "app/services/content_vault_indexer.py",
    ROOT / "app/services/local_folder_indexer.py",
    ROOT / "app/services/wordpress_sync.py",
)
FORBIDDEN = (
    "save_to_external_docs(",
    "INSERT INTO external_docs",
    "UPDATE external_docs",
    "DELETE FROM external_docs",
    "FROM external_docs",
)


def test_product_entries_do_not_own_external_docs_sql() -> None:
    candidates = [
        *LEGACY_SERVICE_PATHS,
        *(ROOT / "app/routes").rglob("*.py"),
        *(ROOT / "features").rglob("*.py"),
    ]
    violations = []
    for path in candidates:
        content = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in content:
                violations.append(f"{path.relative_to(ROOT)}:{token}")
    assert violations == []


@pytest.mark.asyncio
async def test_retired_vector_write_leaf_fails_closed() -> None:
    with pytest.raises(
        ValueError,
        match="direct_external_docs_write_retired_use_projection_facade",
    ):
        await VectorSearchService().save_to_external_docs({})
