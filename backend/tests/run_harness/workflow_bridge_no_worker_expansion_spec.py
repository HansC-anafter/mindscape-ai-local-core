import inspect

from backend.app.services.run_harness import workflow_execution_service
from backend.app.services.run_harness import workflow_ledger_bridge


def test_workflow_bridge_does_not_mutate_resource_pools() -> None:
    service_source = inspect.getsource(workflow_execution_service)
    bridge_source = inspect.getsource(workflow_ledger_bridge)
    combined = service_source + bridge_source

    forbidden_fragments = [
        "queue_partition",
        "worker_target",
        "pgbouncer",
        "polling",
        "create_task(",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in combined
