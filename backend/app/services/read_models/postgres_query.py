"""PostgreSQL executor for manifest-declared read models."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase

from .keyset import decode_cursor, encode_cursor
from .query_spec import ReadModelPage, ReadModelQuerySpec


class PostgresReadModelStore(PostgresStoreBase):
    """Execute read-model queries without accepting raw SQL from routes."""

    def __init__(
        self,
        contract: dict[str, Any],
        *,
        count_contract: dict[str, Any] | None = None,
        cursor_secret: str,
        db_role: str = "core",
    ) -> None:
        super().__init__(db_role=db_role)
        self.contract = contract
        self.count_contract = count_contract
        self.cursor_secret = cursor_secret

    def list_page(self, spec: ReadModelQuerySpec) -> ReadModelPage:
        if spec.read_model_id != self.contract["id"]:
            raise ValueError("read_model_id mismatch")
        sql, params, order_fields = self._compile_select(spec)
        with self.get_connection() as conn:
            rows = [dict(row._mapping) for row in conn.execute(text(sql), params).fetchall()]
            has_next = len(rows) > spec.limit
            page_rows = rows[: spec.limit]
            next_cursor = None
            if has_next and page_rows:
                last = page_rows[-1]
                next_cursor = encode_cursor(
                    read_model_id=self.contract["id"],
                    contract_version=self.contract["contract_version"],
                    sort_id=spec.sort_id,
                    filters=spec.filters,
                    last_values={field: last.get(field) for field in order_fields},
                    ttl_seconds=self.contract["cursor"]["ttl_seconds"],
                    secret=self.cursor_secret,
                )
            counts = self._load_counts(conn, spec) if spec.include_counts else {}
        return ReadModelPage(items=page_rows, next_cursor=next_cursor, counts=counts)

    def _compile_select(self, spec: ReadModelQuerySpec) -> tuple[str, dict[str, Any], list[str]]:
        fields = {field["id"]: field for field in self.contract["fields"]}
        filters = {item["id"]: item for item in self.contract.get("filters", [])}
        sorts = {item["id"]: item for item in self.contract["sorts"]}
        if spec.sort_id not in sorts:
            raise ValueError(f"unknown sort id: {spec.sort_id}")
        if spec.limit <= 0:
            raise ValueError("limit must be positive")
        select_columns = ", ".join(
            f"{field['column']} AS {field['id']}" for field in self.contract["fields"]
        )
        where_parts: list[str] = []
        params: dict[str, Any] = {"limit_plus_one": spec.limit + 1}
        for filter_id, value in spec.filters.items():
            if filter_id not in filters:
                raise ValueError(f"unknown filter id: {filter_id}")
            filter_spec = filters[filter_id]
            field = fields[filter_spec["field"]]
            param_name = f"filter_{filter_id}"
            operator = filter_spec.get("operator", "eq")
            if operator == "eq":
                where_parts.append(f"{field['column']} = :{param_name}")
                params[param_name] = value
            elif operator == "ilike":
                where_parts.append(f"{field['column']} ILIKE :{param_name}")
                params[param_name] = f"%{value}%"
            elif operator == "prefix":
                where_parts.append(f"{field['column']} ILIKE :{param_name}")
                params[param_name] = f"{value}%"
            elif operator == "is_null":
                where_parts.append(f"{field['column']} IS NULL")
            elif operator == "is_not_null":
                where_parts.append(f"{field['column']} IS NOT NULL")
            else:
                raise ValueError(f"unsupported filter operator: {operator}")
        for filter_spec in filters.values():
            if filter_spec.get("required") and filter_spec["id"] not in spec.filters:
                raise ValueError(f"missing required filter: {filter_spec['id']}")

        order_parts: list[str] = []
        order_fields: list[str] = []
        sort = sorts[spec.sort_id]
        for sort_field in sort["fields"]:
            field_id = sort_field["field"]
            field = fields[field_id]
            direction = sort_field["direction"].upper()
            nulls = sort_field.get("nulls")
            nulls_sql = f" NULLS {nulls.upper()}" if nulls else ""
            order_parts.append(f"{field['column']} {direction}{nulls_sql}")
            order_fields.append(field_id)

        cursor_predicate = self._compile_cursor_predicate(spec, sort, fields, params)
        if cursor_predicate:
            where_parts.append(cursor_predicate)
        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        sql = (
            f"SELECT {select_columns} FROM {self.contract['table']}"
            f"{where_sql} ORDER BY {', '.join(order_parts)} LIMIT :limit_plus_one"
        )
        return sql, params, order_fields

    def _compile_cursor_predicate(
        self,
        spec: ReadModelQuerySpec,
        sort: dict[str, Any],
        fields: dict[str, dict[str, Any]],
        params: dict[str, Any],
    ) -> str | None:
        if not spec.cursor:
            return None
        envelope = decode_cursor(
            spec.cursor,
            read_model_id=self.contract["id"],
            contract_version=self.contract["contract_version"],
            sort_id=spec.sort_id,
            filters=spec.filters,
            secret=self.cursor_secret,
        )
        parts: list[str] = []
        previous_equals: list[str] = []
        for index, sort_field in enumerate(sort["fields"]):
            field_id = sort_field["field"]
            column = fields[field_id]["column"]
            param_name = f"cursor_{index}"
            params[param_name] = envelope.last_values.get(field_id)
            direction = sort_field["direction"]
            comparator = ">" if direction == "asc" else "<"
            parts.append(
                "("
                + " AND ".join(previous_equals + [f"{column} {comparator} :{param_name}"])
                + ")"
            )
            previous_equals.append(f"{column} = :{param_name}")
        return "(" + " OR ".join(parts) + ")"

    def _load_counts(self, conn: Any, spec: ReadModelQuerySpec) -> dict[str, Any]:
        if not self.count_contract:
            return {}
        key_columns = self.count_contract["key_columns"]
        where_parts: list[str] = []
        params: dict[str, Any] = {}
        for key in key_columns:
            if key in spec.filters:
                params[key] = spec.filters[key]
                where_parts.append(f"{key} = :{key}")
        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        measures = self.count_contract["measures"]
        select_columns = ", ".join(key_columns + measures)
        sql = f"SELECT {select_columns} FROM {self.count_contract['table']}{where_sql}"
        rows = [dict(row._mapping) for row in conn.execute(text(sql), params).fetchall()]
        return {"rows": rows}
