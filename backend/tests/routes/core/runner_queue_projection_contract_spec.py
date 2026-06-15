from pathlib import Path


def test_runner_queue_producers_persist_and_return_queued_status():
    repo_root = Path(__file__).resolve().parents[4]
    control_route = (
        repo_root
        / "backend"
        / "app"
        / "routes"
        / "core"
        / "playbook_execution_core"
        / "control_routes.py"
    ).read_text(encoding="utf-8")
    rerun_route = (
        repo_root
        / "backend"
        / "app"
        / "routes"
        / "core"
        / "playbook_rerun.py"
    ).read_text(encoding="utf-8")

    assert 'status="queued",\n                            phase="queue"' in control_route
    assert '"status": "queued",\n                    "result": {' in control_route
    assert '"status": "queued",\n                        "execution_id"' in control_route
    assert 'status="queued",\n                            phase="queue"' in rerun_route
