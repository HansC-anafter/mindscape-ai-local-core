"""Neutral, parameterized facet filter compiler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .contracts import FacetFilter


@dataclass(frozen=True)
class CompiledFacetFilters:
    sql: str
    parameters: tuple[Any, ...]


_COMPARISON_SQL = {
    "eq": "=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


def _typed_value(value: Any) -> tuple[str, Any]:
    if isinstance(value, bool):
        return "bool_value", value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number_value", float(value)
    return "text_or_ref", str(value)


def _column_sql(alias: str, column: str) -> str:
    if column == "text_or_ref":
        return f"COALESCE({alias}.text_value, {alias}.ref_value)"
    return f"{alias}.{column}"


def compile_facet_filters(
    predicates: Iterable[FacetFilter],
    *,
    record_alias: str = "record",
) -> CompiledFacetFilters:
    clauses: list[str] = []
    parameters: list[Any] = []
    for index, predicate in enumerate(predicates):
        alias = f"predicate_{index}"
        if predicate.operator == "in":
            values = list(predicate.value)
            columns = {_typed_value(value)[0] for value in values}
            if len(columns) != 1:
                raise ValueError("knowledge_query_facet_in_type_mismatch")
            column = next(iter(columns))
            value_sql = _column_sql(alias, column)
            clauses.append(
                "EXISTS ("
                "SELECT 1 FROM knowledge_projection_facets "
                f"AS {alias} "
                f"WHERE {alias}.projection_record_id = "
                f"{record_alias}.projection_record_id "
                f"AND {alias}.facet_key = %s "
                f"AND {value_sql} = ANY(%s)"
                ")"
            )
            parameters.extend(
                [
                    predicate.key,
                    [_typed_value(value)[1] for value in values],
                ]
            )
            continue
        column, value = _typed_value(predicate.value)
        value_sql = _column_sql(alias, column)
        clauses.append(
            "EXISTS ("
            "SELECT 1 FROM knowledge_projection_facets "
            f"AS {alias} "
            f"WHERE {alias}.projection_record_id = "
            f"{record_alias}.projection_record_id "
            f"AND {alias}.facet_key = %s "
            f"AND {value_sql} "
            f"{_COMPARISON_SQL[predicate.operator]} %s"
            ")"
        )
        parameters.extend([predicate.key, value])
    return CompiledFacetFilters(
        sql=" AND ".join(clauses) if clauses else "TRUE",
        parameters=tuple(parameters),
    )


__all__ = ["CompiledFacetFilters", "compile_facet_filters"]
