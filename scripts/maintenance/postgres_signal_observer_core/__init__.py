"""Bounded PostgreSQL SIGQUIT sender observer implementation."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_GROUPS = {
    "artifact": ("canonical_observer_artifact_sha256",),
    "drill": (
        "DRILL_APPLICATION_NAME",
        "DisposableDrillClientConfig",
        "DisposableDrillSignalConfig",
        "POSTGRES_BACKEND_PID_MAX",
        "POSTGRES_SIGNAL_NAME",
        "POSTGRES_SIGNAL_OUTPUT_BUDGET_BYTES",
        "POSTGRES_SIGNAL_SENDER_EXECUTABLE",
        "POSTGRES_SIGNAL_SENDER_USER",
        "POSTGRES_SIGNAL_TERMINAL_DEADLINE_SECONDS",
        "launch_disposable_drill_client",
        "send_disposable_drill_signal",
    ),
    "drill_bootstrap": (
        "PGBOUNCER_DECLARED_VOLUME_TMPFS",
        "POSTGRES_DATA_TMPFS",
        "DisposableDrillBootstrapConfig",
        "canonical_disposable_drill_temp_root",
    ),
    "drill_admin_url": (
        "DisposableDrillObserverEnvironment",
        "PGBOUNCER_ADMIN_ENVIRONMENT_KEY",
        "serialize_disposable_pgbouncer_config",
        "serialize_disposable_pgbouncer_userlist",
    ),
    "drill_escalation": (
        "FORMAL_DOCKER_OPERATION_CLASSES",
        "POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS",
        "execute_formal_postgres_bootstrap",
        "serialize_postgres_bootstrap_environment",
        "validate_formal_exec_result",
    ),
    "drill_formal_sequence": (
        "FORMAL_DRILL_CLEANUP_ORDER",
        "FORMAL_DRILL_SEQUENCE_ORDER",
        "FORMAL_DRILL_TERMINAL_COMPLETE",
        "FormalDockerExecutionEnvelope",
        "FormalDrillSequenceDefinition",
        "canonical_formal_drill_sequence",
        "execute_formal_drill_sequence",
        "materialize_formal_signal_envelope",
    ),
    "drill_formal_cli": (
        "FORMAL_FULL_SEQUENCE_ENTRY",
        "LEGACY_FORMAL_MUTATION_ENTRY_FAILURE",
        "FormalDrillCliConfig",
        "build_formal_drill_cli_config",
        "execute_canonical_formal_drill",
    ),
    "drill_docker_runtime": (
        "CANONICAL_DOCKER_CLI_ENTRY_PATH",
        "CANONICAL_DOCKER_CLI_TARGET_PATH",
        "FormalExecutorDockerRuntimeContract",
        "canonical_docker_argv",
        "validate_canonical_docker_argv",
    ),
    "drill_images": (
        "OBSERVER_BACKEND_IMAGE_ROLE",
        "POSTGRES_DRILL_IMAGE_ROLE",
        "DisposableDrillImageContract",
        "drill_image_digest",
        "validate_drill_image_ref",
    ),
    "drill_observer": (
        "DisposableDrillObserverConfig",
        "launch_disposable_drill_observer",
    ),
    "drill_readback": (
        "CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS",
        "DisposableDrillContainerReadbackContract",
        "execute_disposable_container_readback",
    ),
    "drill_readback_projection": (
        "CONTAINER_READBACK_MAX_BYTES",
        "CONTAINER_READBACK_ROLES",
        "CONTAINER_READBACK_SCHEMA_VERSION",
        "container_readback_argv",
        "container_readback_projection_format",
        "parse_container_readback_projection",
    ),
    "drill_preconditions": (
        "secure_create_precondition",
        "secure_precondition_readback",
    ),
    "drill_names": (
        "DISPOSABLE_DRILL_NAME_PATTERN",
        "DRILL_SUFFIX_PATTERN",
        "canonical_disposable_drill_name",
        "normalize_disposable_drill_suffix",
        "validate_disposable_drill_name",
    ),
    "drill_runtime": ("FormalExecutorPythonRuntimeContract",),
    "evidence": (
        "EvidenceBudget",
        "EvidenceCapacityExhausted",
        "ObserverEvidenceStore",
    ),
    "events": (
        "SignalGenerateEvent",
        "parse_signal_generate_line",
        "read_namespace_pids",
    ),
    "pgbouncer": ("PgBouncerCorrelationClient",),
    "service": ("ObserverConfig", "PostgresSignalObserver"),
    "tracefs": ("SIGNAL_FILTER", "TraceFsInstance"),
}

_EXPORT_MODULES = {
    name: module_name
    for module_name, names in _EXPORT_GROUPS.items()
    for name in names
}

__all__ = tuple(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{module_name}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
