from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_browser_runners_restore_six_slots_with_per_runner_bounds() -> None:
    compose = yaml.safe_load(
        (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = [
        compose["services"]["runner-default-local-browser"],
        compose["services"]["runner-browser"],
        compose["services"]["runner-browser-extra"],
    ]

    assert all(
        service["environment"]["LOCAL_CORE_RUNNER_MAX_INFLIGHT"].endswith(":-2}")
        for service in services
    )
    assert sum(2 for _service in services) == 6

    for service in services:
        assert "mem_limit" not in service
        assert "cpus" not in service
        assert "pids_limit" not in service
