"""The knowledge shard must reuse one bounded existing runner lane."""

import os
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = Path(
    os.getenv(
        "KNOWLEDGE_RUNNER_COMPOSE_PATH",
        str(REPO_ROOT / "docker-compose.yml"),
    )
)


def test_knowledge_indexing_reuses_the_single_inflight_mlx_dev_runner() -> None:
    compose = yaml.safe_load(
        COMPOSE_PATH.read_text()
    )
    services = compose["services"]
    assert not any(
        service_name.startswith("runner-knowledge")
        for service_name in services
    )

    runner = services["runner-vision-mlx-dev"]["environment"]
    partitions = runner["LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS"]
    assert partitions.endswith(
        ":-vision_mlx_dev,knowledge_indexing}"
    )
    assert runner["LOCAL_CORE_RUNNER_ACCEPTED_RESOURCE_CLASSES"].endswith(
        ":-compute}"
    )
    assert runner["LOCAL_CORE_RUNNER_MAX_INFLIGHT"].endswith(":-1}")
