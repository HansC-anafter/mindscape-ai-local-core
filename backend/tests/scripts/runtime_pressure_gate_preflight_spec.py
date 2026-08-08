from argparse import Namespace
import json

from scripts.maintenance import runtime_pressure_gate


def _args(output_json):
    return Namespace(
        api_base="http://localhost:8200",
        running_observation_limit=100,
        pending_observation_limit=1000,
        action="runner-rolling-reload",
        target_runner_container="mindscape-ai-local-core-runner-browser",
        allow_sole_owner_target=False,
        max_postgres_cpu=200.0,
        max_runner_cpu_ratio=0.9,
        runner_cpu_samples=5,
        runner_cpu_sustained_samples=3,
        runner_cpu_sample_interval_seconds=2.0,
        max_endpoint_seconds=5.0,
        command_timeout_seconds=8.0,
        endpoint_timeout_seconds=5.0,
        pgbouncer_samples=3,
        pgbouncer_sample_interval_seconds=30.0,
        output_json=output_json,
    )


def test_task_status_failure_stops_before_expensive_gate_collectors(
    monkeypatch,
    tmp_path,
    capsys,
):
    output_json = tmp_path / "gate.json"
    monkeypatch.setattr(runtime_pressure_gate, "parse_args", lambda: _args(output_json))
    monkeypatch.setattr(
        runtime_pressure_gate,
        "collect_task_status_counts",
        lambda *_args, **_kwargs: {
            "ok": False,
            "error": "ERROR: canceling statement due to statement timeout",
            "elapsed_seconds": 2.1,
        },
    )

    def unexpected_collector(*_args, **_kwargs):
        raise AssertionError("expensive collector ran after task preflight failure")

    monkeypatch.setattr(
        runtime_pressure_gate,
        "collect_runner_capacity",
        unexpected_collector,
    )

    assert runtime_pressure_gate.main() == 2

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload == json.loads(capsys.readouterr().out)
    assert payload["gate_stage"] == "task_status_preflight"
    assert payload["failures"] == ["task_status_unavailable"]
    assert payload["pgbouncer_metrics"] == {
        "ok": False,
        "reason": "task_status_preflight_failed",
        "skipped": True,
    }
    assert payload["scope"] == {
        "action": "runner-rolling-reload",
        "allow_sole_owner_target": False,
        "target_runner_container": "mindscape-ai-local-core-runner-browser",
    }
