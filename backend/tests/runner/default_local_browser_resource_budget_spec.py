from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_default_local_browser_runner_has_bounded_single_task_budget() -> None:
    compose = yaml.safe_load(
        (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )
    service = compose["services"]["runner-default-local-browser"]
    environment = service["environment"]

    assert environment["LOCAL_CORE_RUNNER_MAX_INFLIGHT"].endswith(":-1}")
    if "LOCAL_CORE_RUNNER_POOL_SIZE" in environment:
        assert environment["LOCAL_CORE_RUNNER_POOL_SIZE"].endswith(":-1}")
    assert service["mem_limit"].endswith(":-6g}")
    assert service["cpus"].endswith(":-4.0}")
    assert service["pids_limit"].endswith(":-256}")
