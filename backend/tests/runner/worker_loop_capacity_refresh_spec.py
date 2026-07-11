from __future__ import annotations

import inspect

from backend.app.runner import worker_loop


def test_capacity_refresh_precedes_heartbeat_and_pause_gates() -> None:
    source = inspect.getsource(worker_loop.run_forever)
    loop_source = source.split("while True:", 1)[1]

    discard_at = loop_source.index("_discard_finished_tasks(inflight)")
    refresh_at = loop_source.index("capacity = resolve_runner_capacity_snapshot(")
    publish_at = loop_source.index("await _publish_resource_heartbeat(")
    instance_gate_at = loop_source.index("if not runner_claiming_enabled:")
    global_gate_at = loop_source.index("if claim_gate_paused:")

    assert discard_at < refresh_at < publish_at
    assert publish_at < instance_gate_at < global_gate_at
    assert loop_source.count("capacity = resolve_runner_capacity_snapshot(") == 1
