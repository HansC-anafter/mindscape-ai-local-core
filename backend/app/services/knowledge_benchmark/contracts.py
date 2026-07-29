"""Strict public service contracts for reusable knowledge benchmarks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.services.tools.knowledge_query.contracts import (
    KnowledgeQueryInput,
)


class BenchmarkQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9_.-]{2,127}$",
    )
    domain_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9-]{1,63}$",
    )
    tier: Literal[
        "quick",
        "contextual",
        "cross_domain",
        "global_ambiguous",
    ]
    benchmark_class: Literal[
        "data_local",
        "activity_local",
        "data_global",
        "activity_global",
    ]
    question_text: str = Field(min_length=1, max_length=8000)
    canonical_request: KnowledgeQueryInput
    rubric: dict[str, Any] = Field(default_factory=dict)
    ordinal: int = Field(ge=1, le=5000)

    @model_validator(mode="after")
    def validate_search_shape(self) -> "BenchmarkQuestion":
        if (
            self.canonical_request.operation != "search"
            or self.canonical_request.scope != "active_group"
        ):
            raise ValueError(
                "knowledge_benchmark_group_search_request_required"
            )
        return self


class BenchmarkCatalogCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=64)
    group_id: str = Field(min_length=1, max_length=64)
    catalog_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9_.-]{2,127}$",
    )
    catalog_revision: str = Field(min_length=1, max_length=128)
    questions: tuple[BenchmarkQuestion, ...] = Field(
        min_length=1,
        max_length=5000,
    )

    @model_validator(mode="after")
    def validate_unique_questions(self) -> "BenchmarkCatalogCommand":
        question_ids = [item.question_id for item in self.questions]
        ordinals = [item.ordinal for item in self.questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("knowledge_benchmark_question_duplicate")
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("knowledge_benchmark_ordinal_duplicate")
        return self


class BenchmarkExecutionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=64)
    group_id: str = Field(min_length=1, max_length=64)
    catalog_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9_.-]{2,127}$",
    )
    catalog_revision: str = Field(min_length=1, max_length=128)
    question_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9_.-]{2,127}$",
    )


__all__ = [
    "BenchmarkCatalogCommand",
    "BenchmarkExecutionCommand",
    "BenchmarkQuestion",
]
