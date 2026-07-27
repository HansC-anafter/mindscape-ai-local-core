"""Benchmark catalog contracts stay deterministic and group-search only."""

import pytest
from pydantic import ValidationError

from backend.app.services.knowledge_benchmark.contracts import (
    BenchmarkCatalogCommand,
)


def _question(question_id: str, ordinal: int):
    return {
        "question_id": question_id,
        "domain_id": "sleep",
        "tier": "quick",
        "benchmark_class": "data_local",
        "question_text": "睡眠規律是否與認知健康有關？",
        "canonical_request": {
            "operation": "search",
            "query": "睡眠規律 認知健康",
            "retrieval_mode": "hybrid",
            "scope": "active_group",
        },
        "rubric": {"positive_patterns": ["睡眠", "認知"]},
        "ordinal": ordinal,
    }


def test_catalog_requires_unique_question_ids_and_ordinals() -> None:
    command = BenchmarkCatalogCommand.model_validate(
        {
            "workspace_id": "workspace-dispatch",
            "group_id": "wg_health",
            "catalog_id": "health.frontier.v1",
            "catalog_revision": "2026-07-27",
            "questions": (
                _question("hwg.sleep.q01", 1),
                _question("hwg.sleep.q02", 2),
            ),
        }
    )

    assert len(command.questions) == 2
    assert command.questions[0].canonical_request.scope == "active_group"


def test_catalog_rejects_non_group_query() -> None:
    raw = _question("hwg.sleep.q01", 1)
    raw["canonical_request"]["scope"] = "workspace"

    with pytest.raises(ValidationError):
        BenchmarkCatalogCommand.model_validate(
            {
                "workspace_id": "workspace-dispatch",
                "group_id": "wg_health",
                "catalog_id": "health.frontier.v1",
                "catalog_revision": "2026-07-27",
                "questions": (raw,),
            }
        )
