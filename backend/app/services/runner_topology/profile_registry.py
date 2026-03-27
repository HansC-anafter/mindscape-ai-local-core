"""Runner profile registry and environment-backed profile resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Optional

from .partitions import (
    BROWSER_LOCAL_QUEUE_PARTITION,
    DEFAULT_LOCAL_QUEUE_PARTITION,
    RUNNER_READY_QUEUE_ORDER,
    VISION_LOCAL_QUEUE_PARTITION,
    normalize_queue_partition,
)

RESOURCE_CLASS_BROWSER = "browser"
RESOURCE_CLASS_COMPUTE = "compute"
RESOURCE_CLASS_API = "api"
_ALL_RESOURCE_CLASSES = (
    RESOURCE_CLASS_COMPUTE,
    RESOURCE_CLASS_BROWSER,
    RESOURCE_CLASS_API,
)


@dataclass(frozen=True)
class RunnerProfile:
    profile_code: str
    display_name: str
    dispatch_mode: str
    accepted_resource_classes: tuple[str, ...]
    accepted_queue_partitions: tuple[str, ...]
    accepted_capability_codes: tuple[str, ...] = ()
    runtime_id: Optional[str] = None
    max_inflight: int = 1
    enabled: bool = True


def _normalize_tokens(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        token = str(value or "").strip()
        if token and token not in normalized:
            normalized.append(token)
    return tuple(normalized)


def _normalize_resource_classes(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        token = str(value or "").strip().lower()
        if token and token not in normalized:
            normalized.append(token)
    return tuple(normalized)


def _normalize_queue_partitions(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        token = normalize_queue_partition(value, fallback=None)
        if token and token not in normalized:
            normalized.append(token)
    return tuple(normalized)


def _parse_csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except Exception:
        return default


def _build_profile(
    *,
    profile_code: str,
    display_name: str,
    dispatch_mode: str = "docker_local",
    accepted_queue_partitions: Iterable[str],
    accepted_resource_classes: Iterable[str],
    accepted_capability_codes: Iterable[str] = (),
    runtime_id: Optional[str] = None,
    max_inflight: int = 1,
    enabled: bool = True,
) -> RunnerProfile:
    normalized_partitions = _normalize_queue_partitions(accepted_queue_partitions)
    if not normalized_partitions:
        normalized_partitions = (DEFAULT_LOCAL_QUEUE_PARTITION,)

    normalized_resource_classes = _normalize_resource_classes(accepted_resource_classes)
    if not normalized_resource_classes:
        normalized_resource_classes = _ALL_RESOURCE_CLASSES

    return RunnerProfile(
        profile_code=profile_code,
        display_name=display_name,
        dispatch_mode=(dispatch_mode or "docker_local").strip() or "docker_local",
        accepted_resource_classes=normalized_resource_classes,
        accepted_queue_partitions=normalized_partitions,
        accepted_capability_codes=_normalize_tokens(accepted_capability_codes),
        runtime_id=(runtime_id or "").strip() or None,
        max_inflight=max(1, int(max_inflight or 1)),
        enabled=bool(enabled),
    )


def get_builtin_runner_profiles(
    *,
    max_inflight: int = 1,
) -> dict[str, RunnerProfile]:
    return {
        "shared_local": _build_profile(
            profile_code="shared_local",
            display_name="Shared Local Runner",
            accepted_queue_partitions=RUNNER_READY_QUEUE_ORDER,
            accepted_resource_classes=_ALL_RESOURCE_CLASSES,
            max_inflight=max_inflight,
        ),
        "default_local": _build_profile(
            profile_code="default_local",
            display_name="Default Local Runner",
            accepted_queue_partitions=(DEFAULT_LOCAL_QUEUE_PARTITION,),
            accepted_resource_classes=(
                RESOURCE_CLASS_COMPUTE,
                RESOURCE_CLASS_API,
            ),
            max_inflight=max_inflight,
        ),
        "browser_local": _build_profile(
            profile_code="browser_local",
            display_name="Browser Local Runner",
            accepted_queue_partitions=(BROWSER_LOCAL_QUEUE_PARTITION,),
            accepted_resource_classes=(RESOURCE_CLASS_BROWSER,),
            max_inflight=max_inflight,
        ),
        "vision_local": _build_profile(
            profile_code="vision_local",
            display_name="Vision Local Runner",
            accepted_queue_partitions=(VISION_LOCAL_QUEUE_PARTITION,),
            accepted_resource_classes=(RESOURCE_CLASS_COMPUTE,),
            max_inflight=max_inflight,
        ),
    }


def resolve_runner_profile_from_env(
    *,
    default_max_inflight: int = 1,
) -> RunnerProfile:
    base_max_inflight = _env_int(
        "LOCAL_CORE_RUNNER_MAX_INFLIGHT",
        max(1, default_max_inflight),
    )
    profile_code = (
        os.getenv("LOCAL_CORE_RUNNER_PROFILE", "").strip() or "shared_local"
    )
    builtin_profiles = get_builtin_runner_profiles(max_inflight=base_max_inflight)
    base_profile = builtin_profiles.get(profile_code) or _build_profile(
        profile_code=profile_code,
        display_name=profile_code.replace("_", " ").strip().title() or "Custom Runner",
        accepted_queue_partitions=RUNNER_READY_QUEUE_ORDER,
        accepted_resource_classes=_ALL_RESOURCE_CLASSES,
        max_inflight=base_max_inflight,
    )

    accepted_queue_partitions = _normalize_queue_partitions(
        _parse_csv_env("LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS")
    ) or base_profile.accepted_queue_partitions
    accepted_resource_classes = _normalize_resource_classes(
        _parse_csv_env("LOCAL_CORE_RUNNER_ACCEPTED_RESOURCE_CLASSES")
    ) or base_profile.accepted_resource_classes
    accepted_capability_codes = _normalize_tokens(
        _parse_csv_env("LOCAL_CORE_RUNNER_ACCEPTED_CAPABILITY_CODES")
    ) or base_profile.accepted_capability_codes

    return RunnerProfile(
        profile_code=profile_code,
        display_name=(
            os.getenv("LOCAL_CORE_RUNNER_DISPLAY_NAME", "").strip()
            or base_profile.display_name
        ),
        dispatch_mode=(
            os.getenv("LOCAL_CORE_RUNNER_DISPATCH_MODE", "").strip()
            or base_profile.dispatch_mode
        ),
        accepted_resource_classes=accepted_resource_classes,
        accepted_queue_partitions=accepted_queue_partitions,
        accepted_capability_codes=accepted_capability_codes,
        runtime_id=(
            os.getenv("LOCAL_CORE_RUNNER_RUNTIME_ID", "").strip()
            or base_profile.runtime_id
        ),
        max_inflight=_env_int("LOCAL_CORE_RUNNER_MAX_INFLIGHT", base_profile.max_inflight),
        enabled=_env_bool("LOCAL_CORE_RUNNER_ENABLED", base_profile.enabled),
    )
