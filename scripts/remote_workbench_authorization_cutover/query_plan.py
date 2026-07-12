"""True-planner evidence for the effective workspace policy query."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from .io import CommandExecutor, CutoverError


SMALL_TABLE_SCAN_BUDGET = 32
BUFFER_BLOCK_BUDGET = 32
EXECUTION_TIME_BUDGET_MS = 100.0


class QueryPlanGate:
    """Require a real ANALYZE/BUFFERS plan without planner overrides."""

    def __init__(self, executor: CommandExecutor) -> None:
        self.executor = executor

    @staticmethod
    def _workspace_nodes(root: dict[str, Any]) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        stack = [root]
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                raise CutoverError("Effective policy query plan node is malformed")
            if node.get("Relation Name") == "workspace_mobile_workbench_gateway_policies":
                nodes.append(node)
            stack.extend(node.get("Plans") or [])
        return nodes

    @staticmethod
    def _bounded_small_scan(node: dict[str, Any]) -> bool:
        numeric = (
            node.get("Plan Rows", 0),
            node.get("Actual Rows", 0),
            node.get("Rows Removed by Filter", 0),
        )
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numeric):
            return False
        blocks = sum(
            value
            for key, value in node.items()
            if key in {"Shared Hit Blocks", "Shared Read Blocks"}
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        )
        return (
            numeric[0] <= SMALL_TABLE_SCAN_BUDGET
            and numeric[1] <= 1
            and numeric[2] <= SMALL_TABLE_SCAN_BUDGET
            and blocks <= BUFFER_BLOCK_BUDGET
        )

    def verify(self, workspace_id: str) -> None:
        """Run the production planner and accept only indexed or bounded tiny scans."""

        try:
            normalized_workspace = str(UUID(workspace_id))
        except ValueError as error:
            raise CutoverError("Workspace id for query-plan verification is invalid") from error
        sql = """
BEGIN;
SELECT EXISTS (
  SELECT 1 FROM pg_indexes
  WHERE schemaname = current_schema()
    AND tablename = 'workspace_mobile_workbench_gateway_policies'
    AND indexdef ~ '\\(workspace_id\\)'
);
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT r.id, r.access_issuer, r.access_audience, r.remote_access_state,
       r.local_core_super_admins, r.revision, w.workspace_id,
       w.allowed_principals, w.allowed_capability_codes
FROM remote_workbench_runtime_access_policies AS r
LEFT JOIN workspace_mobile_workbench_gateway_policies AS w
  ON w.workspace_id = :'workspace_id'
WHERE r.id = 'remote-workbench-runtime';
ROLLBACK;
""".strip()
        raw = self.executor.run(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-postgres",
                "psql",
                "-XqAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                f"workspace_id={normalized_workspace}",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-c",
                sql,
            ],
            timeout_seconds=30.0,
        ).strip()
        first_line = raw.splitlines()[0] if raw else ""
        start = raw.find("[")
        if first_line not in {"t", "true"} or start < 0:
            raise CutoverError("Workspace policy index evidence is missing")
        try:
            payload = json.loads(raw[start:])
            statement = payload[0]
            root = statement["Plan"]
            execution_time = statement["Execution Time"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise CutoverError("Effective policy query plan is malformed") from error
        if (
            isinstance(execution_time, bool)
            or not isinstance(execution_time, (int, float))
            or execution_time < 0
            or execution_time > EXECUTION_TIME_BUDGET_MS
        ):
            raise CutoverError("Effective policy query execution time exceeds its budget")
        nodes = self._workspace_nodes(root)
        if len(nodes) != 1:
            raise CutoverError("Effective policy plan must scan the workspace policy once")
        node = nodes[0]
        node_type = node.get("Node Type")
        if node_type in {"Index Scan", "Index Only Scan", "Bitmap Heap Scan"}:
            return
        if node_type == "Seq Scan" and self._bounded_small_scan(node):
            return
        raise CutoverError("Effective policy query uses an unbounded workspace scan")
