from contextlib import contextmanager
from types import SimpleNamespace

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.services.runner_topology import queue_partition_matches


def build_task(
    *,
    visibility: str = "background",
    auto_triggered: bool = True,
    pack_id: str = "ig_analyze_pinned_reference",
    queue_shard: str = "vision_local",
    producer_kind: str = "pin_reference",
    task_id: str | None = None,
    concurrency_key: str | None = None,
) -> Task:
    execution_context = {
        "auto_triggered": auto_triggered,
        "playbook_code": pack_id,
        "concurrency": {
            "lock_scope": "playbook",
            "max_parallel": 1,
        },
        "admission_policy": {
            "mode": "auto" if auto_triggered else "manual",
            "visibility": visibility,
            "producer_kind": producer_kind,
        },
    }
    return Task(
        id=task_id or f"task-{visibility}",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id=f"exec-{visibility}",
        pack_id=pack_id,
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard=queue_shard,
        concurrency_key=concurrency_key,
        created_at=_utc_now(),
        execution_context=execution_context,
    )


class MemoryTasksStore:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.single_flight_queries: list[str] = []

    @contextmanager
    def get_connection(self):
        yield _MemoryTaskPressureConnection(self.rows, self.single_flight_queries)

    def insert_rows(self, *rows: dict) -> None:
        self.rows.extend(dict(row) for row in rows)


class _MemoryTaskPressureResult:
    def __init__(self, row: SimpleNamespace) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _MemoryTaskPressureConnection:
    def __init__(self, rows: list[dict], single_flight_queries: list[str]) -> None:
        self.rows = rows
        self.single_flight_queries = single_flight_queries

    def execute(self, query, params):
        query_text = str(query)
        if "concurrency_key = :concurrency_key" in query_text:
            query_kind = (
                "pending" if "status = :pending_status" in query_text else "running"
            )
            self.single_flight_queries.append(query_kind)
            return _MemoryTaskPressureResult(
                self._single_flight_conflict(params, query_kind)
            )
        if "pending_total" in query_text:
            return _MemoryTaskPressureResult(self._pending_pressure(params))
        if "running_total" in query_text:
            return _MemoryTaskPressureResult(self._running_pressure(params))
        raise AssertionError(f"Unexpected pressure query: {query_text}")

    def _matches_queue(self, row: dict, params: dict) -> bool:
        queue_shard = row.get("queue_shard")
        expected = params.get("queue_partition_0")
        return queue_partition_matches(queue_shard, expected)

    def _pending_pressure(self, params: dict) -> SimpleNamespace:
        now = params["now"]
        pending_rows = [
            row
            for row in self.rows
            if row.get("task_type")
            in {params["task_type_pb"], params["task_type_tool"]}
            and row.get("status") == params["pending_status"]
            and (row.get("blocked_reason") in {None, params["unblocked_reason"]})
            and row.get("next_eligible_at") <= now
            and row.get("frontier_state") == params["ready_frontier_state"]
            and self._matches_queue(row, params)
            and self._matches_pressure_scope(row, params)
        ]
        oldest = None
        if pending_rows:
            oldest = min(
                row.get("frontier_enqueued_at")
                or row.get("next_eligible_at")
                or row.get("created_at")
                for row in pending_rows
            )
        return SimpleNamespace(
            pending_total=len(pending_rows),
            oldest_pending_at=oldest,
        )

    def _running_pressure(self, params: dict) -> SimpleNamespace:
        running_rows = [
            row
            for row in self.rows
            if row.get("task_type")
            in {params["task_type_pb"], params["task_type_tool"]}
            and row.get("status") == params["running_status"]
            and self._matches_queue(row, params)
            and self._matches_pressure_scope(row, params)
        ]
        return SimpleNamespace(running_total=len(running_rows))

    def _matches_pressure_scope(self, row: dict, params: dict) -> bool:
        lane_key = params.get("admission_pressure_lane_key")
        if not lane_key:
            return True
        context = row.get("execution_context")
        if not isinstance(context, dict):
            context = {}
        row_lane = (
            context.get("fairness_lane_key")
            or context.get("playbook_code")
            or row.get("pack_id")
        )
        return row_lane == lane_key

    def _single_flight_conflict(self, params: dict, query_kind: str):
        for row in sorted(self.rows, key=lambda item: (item["created_at"], item["id"])):
            if row.get("id") == params["task_id"]:
                continue
            if row.get("concurrency_key") != params["concurrency_key"]:
                continue
            if row.get("task_type") not in {
                params["task_type_pb"],
                params["task_type_tool"],
            }:
                continue
            if (
                query_kind == "running"
                and row.get("status") == params["running_status"]
                and row.get("frontier_state")
                in {None, params["running_frontier_state"]}
            ):
                return SimpleNamespace(
                    id=row.get("id"),
                    status=row.get("status"),
                    frontier_state=row.get("frontier_state"),
                )
            if query_kind == "pending" and (
                row.get("status") == params["pending_status"]
                and row.get("frontier_state")
                in {params["ready_frontier_state"], params["running_frontier_state"]}
                and row.get("blocked_reason") in {None, params["unblocked_reason"]}
                and row.get("next_eligible_at") <= params["now"]
            ):
                return SimpleNamespace(
                    id=row.get("id"),
                    status=row.get("status"),
                    frontier_state=row.get("frontier_state"),
                )
        return None


def task_row(
    *,
    task_id: str,
    status: str,
    created_at,
    pack_id: str = "ig_analyze_pinned_reference",
    queue_shard: str = "browser_local",
    concurrency_key: str | None = None,
    blocked_reason: str | None = None,
    next_eligible_at=None,
    frontier_state: str | None = None,
    frontier_enqueued_at=None,
    execution_context: dict | None = None,
) -> dict:
    return {
        "id": task_id,
        "pack_id": pack_id,
        "task_type": "playbook_execution",
        "status": status,
        "blocked_reason": blocked_reason,
        "queue_shard": queue_shard,
        "concurrency_key": concurrency_key,
        "created_at": created_at,
        "next_eligible_at": next_eligible_at or created_at,
        "frontier_state": frontier_state,
        "frontier_enqueued_at": frontier_enqueued_at,
        "execution_context": execution_context or {"playbook_code": pack_id},
    }
