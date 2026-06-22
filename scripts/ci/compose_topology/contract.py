"""Compose topology contract constants and parsers."""

from __future__ import annotations

import configparser
import shlex
from dataclasses import dataclass


COMPOSE_FILE = "docker-compose.yml"
PGBOUNCER_CONFIG = "docker/pgbouncer/pgbouncer.ini"
SERVICE_ENDPOINT_SEED = "config/service-endpoints.seed.json"

PROFILE_SETS: dict[str, tuple[str, ...]] = {
    "default": (),
    "control-plane": ("control-plane",),
    "ha": ("ha",),
    "spillover": ("spillover",),
    "ocr": ("ocr",),
    "all-profiles": ("control-plane", "spillover", "ha", "ocr"),
}

DEFAULT_SERVICES = {
    "postgres",
    "pgbouncer",
    "redis",
    "backend",
    "runner-browser",
    "runner-default-local-browser",
    "runner-vision-mlx-dev",
    "xtts-service",
    "media-proxy",
    "runner-browser-extra",
    "runner-vision",
    "whisper-service",
}
CONTROL_SERVICES = DEFAULT_SERVICES | {"backend-control", "frontend"}
HA_SERVICES = DEFAULT_SERVICES | {"postgres-replica"}
SPILLOVER_SERVICES = DEFAULT_SERVICES | {"runner-spillover"}
OCR_SERVICES = DEFAULT_SERVICES | {"ocr-service"}
ALL_SERVICES = CONTROL_SERVICES | {"runner-spillover", "postgres-replica", "ocr-service"}

EXPECTED_SERVICES_BY_PROFILE = {
    "default": DEFAULT_SERVICES,
    "control-plane": CONTROL_SERVICES,
    "ha": HA_SERVICES,
    "spillover": SPILLOVER_SERVICES,
    "ocr": OCR_SERVICES,
    "all-profiles": ALL_SERVICES,
}

CORE_DEPENDENCIES = ("postgres", "pgbouncer", "redis")
RUNNER_DEPENDENCIES = ("backend", "pgbouncer", "redis")

RUNNER_EXPECTATIONS = {
    "runner-default-local-browser": {
        "profile": "default_local_browser",
        "accepted_partitions": "default_local_browser",
        "max_inflight": "3",
        "pool_size": "4",
        "max_overflow": "1",
    },
    "runner-browser": {
        "profile": "browser_local",
        "accepted_partitions": "browser_local",
        "max_inflight": "3",
        "pool_size": "4",
        "max_overflow": "1",
    },
    "runner-browser-extra": {
        "profile": "browser_local",
        "accepted_partitions": "browser_local",
        "max_inflight": "3",
        "pool_size": "4",
        "max_overflow": "1",
    },
    "runner-vision": {
        "profile": "vision_local",
        "accepted_partitions": "vision_local",
        "max_inflight": "3",
        "pool_size": "4",
        "max_overflow": "1",
    },
    "runner-vision-mlx-dev": {
        "profile": "vision_mlx_dev",
        "accepted_partitions": "vision_mlx_dev",
        "max_inflight": "1",
        "pool_size": "2",
        "max_overflow": "0",
    },
    "runner-spillover": {
        "profile": "default_local",
        "accepted_partitions": "default_local",
        "max_inflight": "1",
        "pool_size": "4",
        "max_overflow": "1",
        "compose_profile": "spillover",
    },
}


@dataclass(frozen=True)
class PgBouncerConfig:
    databases: dict[str, dict[str, str]]
    pgbouncer: dict[str, str]


def parse_pgbouncer_config(source: str) -> PgBouncerConfig:
    parser = configparser.ConfigParser()
    parser.read_string(source)
    databases: dict[str, dict[str, str]] = {}
    if parser.has_section("databases"):
        for database, value in parser.items("databases"):
            properties: dict[str, str] = {}
            for token in shlex.split(value):
                key, separator, item_value = token.partition("=")
                if separator:
                    properties[key] = item_value
            databases[database] = properties
    pgbouncer = dict(parser.items("pgbouncer")) if parser.has_section("pgbouncer") else {}
    return PgBouncerConfig(databases=databases, pgbouncer=pgbouncer)
