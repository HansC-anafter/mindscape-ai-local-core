"""Executable composition graph runner."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Sequence

from backend.app.models.object_runtime import (
    CompositionGraphDiagnostic,
    CompositionGraphEdge,
    CompositionGraphNode,
    CompositionGraphNodeProviderNode,
    CompositionGraphRun,
    CompositionGraphRunNodeState,
)
from backend.app.services.object_runtime.common import _invoke_backend_callable
from backend.app.services.object_runtime.composition_graph_node_registry import (
    render_runtime_lock_key,
)
from backend.app.services.object_runtime.composition_graph_run_store import (
    CompositionGraphRunStore,
    utc_iso,
)

CORE_OBJECT_REFERENCE_NODE_TYPE = "object_reference"
_RUNTIME_LOCKS: Dict[str, asyncio.Semaphore] = {}


class CompositionGraphRunner:
    """Run an executable graph through pack-owned node executors."""

    def __init__(
        self,
        *,
        run_store: CompositionGraphRunStore,
        provider_nodes: Dict[str, CompositionGraphNodeProviderNode],
    ) -> None:
        self.run_store = run_store
        self.provider_nodes = provider_nodes
        self._state_lock = asyncio.Lock()

    async def run(self, run: CompositionGraphRun) -> CompositionGraphRun:
        self._run = self.run_store.update_run(
            run.model_copy(
                update={
                    "status": "running",
                    "started_at": run.started_at or utc_iso(),
                    "updated_at": utc_iso(),
                }
            )
        )
        try:
            await self._run_dag()
        except Exception as exc:
            diagnostic = self._diagnostic(
                "graph_run_failed",
                f"Composition graph run failed: {exc}",
            )
            self._run = self.run_store.update_run(
                self._run.model_copy(
                    update={
                        "status": "failed",
                        "completed_at": utc_iso(),
                        "diagnostics": [*self._run.diagnostics, diagnostic],
                    }
                )
            )
        return self._run

    async def _run_dag(self) -> None:
        node_by_id = {node.id: node for node in self._run.nodes}
        node_order = [node.id for node in self._run.nodes]
        incoming, outgoing, in_degree = self._build_graph(self._run.nodes, self._run.edges)
        ready = deque([node_id for node_id in node_order if in_degree[node_id] == 0])
        completed: set[str] = set()

        while ready:
            batch = list(ready)
            ready.clear()
            await asyncio.gather(
                *(self._execute_node(node_by_id[node_id], incoming[node_id]) for node_id in batch)
            )
            for node_id in batch:
                completed.add(node_id)
                for target_id in outgoing[node_id]:
                    in_degree[target_id] -= 1
                    if in_degree[target_id] == 0:
                        ready.append(target_id)

        if len(completed) != len(node_by_id):
            diagnostic = self._diagnostic(
                "graph_cycle_detected",
                "Composition graph run requires an acyclic graph.",
            )
            self._run = self.run_store.update_run(
                self._run.model_copy(
                    update={
                        "status": "failed",
                        "completed_at": utc_iso(),
                        "diagnostics": [*self._run.diagnostics, diagnostic],
                    }
                )
            )
            return

        node_statuses = {state.status for state in self._run.node_states.values()}
        if "failed" in node_statuses or "skipped" in node_statuses:
            final_status = "failed"
        elif "waiting" in node_statuses:
            final_status = "waiting"
        else:
            final_status = "succeeded"
        self._run = self.run_store.update_run(
            self._run.model_copy(
                update={
                    "status": final_status,
                    "completed_at": utc_iso() if final_status != "waiting" else None,
                    "outputs": self._collect_terminal_outputs(),
                }
            )
        )

    async def _execute_node(
        self,
        node: CompositionGraphNode,
        incoming_edges: Sequence[CompositionGraphEdge],
    ) -> None:
        input_values = self._input_values(incoming_edges)
        blocked = self._first_failed_upstream(incoming_edges)
        if blocked is not None:
            await self._set_node_state(
                node.id,
                status="skipped",
                input_values=input_values,
                diagnostics=[
                    self._diagnostic(
                        "upstream_node_failed",
                        "Node skipped because an upstream node did not succeed.",
                        node_id=node.id,
                        metadata={"upstream_node_id": blocked},
                    )
                ],
                completed=True,
            )
            return

        provider = self.provider_nodes.get(node.type)
        if node.type == CORE_OBJECT_REFERENCE_NODE_TYPE:
            await self._set_node_state(
                node.id,
                status="running",
                input_values=input_values,
                started=True,
            )
            await self._set_node_state(
                node.id,
                status="succeeded",
                outputs={"object": node.payload.get("ref")},
                completed=True,
            )
            return
        if provider is None:
            await self._set_node_state(
                node.id,
                status="failed",
                input_values=input_values,
                diagnostics=[
                    self._diagnostic(
                        "unknown_node_executor",
                        "Node type has no executable provider.",
                        node_id=node.id,
                        metadata={"node_type": node.type},
                    )
                ],
                completed=True,
            )
            return

        lock_key = None
        if provider.runtime_lock is not None:
            lock_key = render_runtime_lock_key(
                provider.runtime_lock.key_template,
                workspace_id=self._run.workspace_id,
                payload=node.payload,
            )
        semaphore = _RUNTIME_LOCKS.setdefault(lock_key, asyncio.Semaphore(1)) if lock_key else None
        if semaphore is None:
            await self._invoke_provider_node(node, provider, input_values)
            return

        async with semaphore:
            await self._invoke_provider_node(node, provider, input_values)

    async def _invoke_provider_node(
        self,
        node: CompositionGraphNode,
        provider: CompositionGraphNodeProviderNode,
        input_values: Dict[str, Any],
    ) -> None:
        await self._set_node_state(
            node.id,
            status="running",
            input_values=input_values,
            started=True,
        )
        try:
            result = await _invoke_backend_callable(
                provider.executor.backend,
                workspace_id=self._run.workspace_id,
                graph_run_id=self._run.id,
                node_id=node.id,
                node_type=node.type,
                payload=node.payload,
                input_values=input_values,
                context={
                    "meeting_id": self._run.meeting_id,
                    "thread_id": self._run.thread_id,
                    "command": self._run.command,
                },
            )
            normalized = self._normalize_node_result(node, result)
        except Exception as exc:
            normalized = {
                "status": "failed",
                "outputs": {},
                "diagnostics": [
                    self._diagnostic(
                        "node_executor_failed",
                        f"Node executor failed: {exc}",
                        node_id=node.id,
                        metadata={"node_type": node.type},
                    )
                ],
                "metadata": {},
            }
        await self._set_node_state(
            node.id,
            status=normalized["status"],
            outputs=normalized["outputs"],
            diagnostics=normalized["diagnostics"],
            metadata=normalized["metadata"],
            completed=normalized["status"] != "waiting",
        )

    async def _set_node_state(
        self,
        node_id: str,
        *,
        status: str,
        input_values: Dict[str, Any] | None = None,
        outputs: Dict[str, Any] | None = None,
        diagnostics: List[CompositionGraphDiagnostic] | None = None,
        metadata: Dict[str, Any] | None = None,
        started: bool = False,
        completed: bool = False,
    ) -> None:
        async with self._state_lock:
            state = self._run.node_states[node_id]
            update: Dict[str, Any] = {"status": status}
            if input_values is not None:
                update["input_values"] = input_values
            if outputs is not None:
                update["outputs"] = self._sanitize_outputs(outputs)
            if diagnostics is not None:
                update["diagnostics"] = diagnostics
            if metadata is not None:
                update["metadata"] = metadata
            if started and state.started_at is None:
                update["started_at"] = utc_iso()
            if completed:
                update["completed_at"] = utc_iso()
            self._run.node_states[node_id] = state.model_copy(update=update)
            self._run = self.run_store.update_run(self._run)

    def _input_values(self, incoming_edges: Sequence[CompositionGraphEdge]) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for edge in incoming_edges:
            source_state = self._run.node_states.get(edge.source)
            if source_state is None:
                continue
            values[edge.target_port] = source_state.outputs.get(edge.source_port)
        return values

    def _first_failed_upstream(
        self,
        incoming_edges: Sequence[CompositionGraphEdge],
    ) -> str | None:
        for edge in incoming_edges:
            source_state = self._run.node_states.get(edge.source)
            if source_state is None:
                return edge.source
            if source_state.status != "succeeded":
                return edge.source
        return None

    def _collect_terminal_outputs(self) -> Dict[str, Any]:
        source_ids = {edge.source for edge in self._run.edges}
        terminal_node_ids = [node.id for node in self._run.nodes if node.id not in source_ids]
        return {
            node_id: self._run.node_states[node_id].outputs
            for node_id in terminal_node_ids
            if node_id in self._run.node_states
        }

    @staticmethod
    def _build_graph(
        nodes: Sequence[CompositionGraphNode],
        edges: Sequence[CompositionGraphEdge],
    ) -> tuple[
        Dict[str, List[CompositionGraphEdge]],
        Dict[str, List[str]],
        Dict[str, int],
    ]:
        node_ids = {node.id for node in nodes}
        incoming: Dict[str, List[CompositionGraphEdge]] = defaultdict(list)
        outgoing: Dict[str, List[str]] = defaultdict(list)
        in_degree: Dict[str, int] = {node.id: 0 for node in nodes}
        for edge in edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                continue
            incoming[edge.target].append(edge)
            outgoing[edge.source].append(edge.target)
            in_degree[edge.target] += 1
        return incoming, outgoing, in_degree

    @staticmethod
    def _normalize_node_result(
        node: CompositionGraphNode,
        result: Any,
    ) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {
                "status": "failed",
                "outputs": {},
                "diagnostics": [
                    CompositionGraphRunner._diagnostic(
                        "invalid_node_executor_result",
                        "Node executor must return an object.",
                        node_id=node.id,
                    )
                ],
                "metadata": {},
            }
        status = str(result.get("status") or "succeeded")
        if status not in {"succeeded", "waiting", "failed", "skipped"}:
            status = "failed"
        diagnostics = [
            item
            if isinstance(item, CompositionGraphDiagnostic)
            else CompositionGraphDiagnostic.model_validate(item)
            for item in list(result.get("diagnostics") or [])
            if isinstance(item, (dict, CompositionGraphDiagnostic))
        ]
        return {
            "status": status,
            "outputs": dict(result.get("outputs") or {}),
            "diagnostics": diagnostics,
            "metadata": dict(result.get("metadata") or {}),
        }

    @staticmethod
    def _sanitize_outputs(outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: CompositionGraphRunner._sanitize_value(value)
            for key, value in outputs.items()
        }

    @staticmethod
    def _sanitize_value(value: Any) -> Any:
        if isinstance(value, str):
            return value if len(value) <= 4096 else value[:4096]
        if isinstance(value, list):
            return [CompositionGraphRunner._sanitize_value(item) for item in value[:1000]]
        if isinstance(value, dict):
            return {
                str(key): CompositionGraphRunner._sanitize_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _diagnostic(
        code: str,
        message: str,
        *,
        node_id: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> CompositionGraphDiagnostic:
        return CompositionGraphDiagnostic(
            code=code,
            message=message,
            severity="error",
            node_id=node_id,
            metadata=metadata or {},
        )
