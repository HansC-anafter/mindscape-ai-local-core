"""Bounded PostgreSQL SIGQUIT sender observer implementation."""

from .artifact import canonical_observer_artifact_sha256
from .drill import (
    DRILL_APPLICATION_NAME,
    DisposableDrillClientConfig,
    DisposableDrillSignalConfig,
    POSTGRES_BACKEND_PID_MAX,
    POSTGRES_SIGNAL_NAME,
    POSTGRES_SIGNAL_OUTPUT_BUDGET_BYTES,
    POSTGRES_SIGNAL_SENDER_EXECUTABLE,
    POSTGRES_SIGNAL_SENDER_USER,
    POSTGRES_SIGNAL_TERMINAL_DEADLINE_SECONDS,
    launch_disposable_drill_client,
    send_disposable_drill_signal,
)
from .drill_bootstrap import (
    PGBOUNCER_DECLARED_VOLUME_TMPFS,
    POSTGRES_DATA_TMPFS,
    DisposableDrillBootstrapConfig,
    canonical_disposable_drill_temp_root,
)
from .drill_admin_url import (
    DisposableDrillObserverEnvironment,
    PGBOUNCER_ADMIN_ENVIRONMENT_KEY,
    serialize_disposable_pgbouncer_config,
    serialize_disposable_pgbouncer_userlist,
)
from .drill_escalation import (
    FORMAL_DOCKER_OPERATION_CLASSES,
    POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS,
    execute_formal_postgres_bootstrap,
    serialize_postgres_bootstrap_environment,
    validate_formal_exec_result,
)
from .drill_formal_sequence import (
    FORMAL_DRILL_CLEANUP_ORDER,
    FORMAL_DRILL_SEQUENCE_ORDER,
    FORMAL_DRILL_TERMINAL_COMPLETE,
    FormalDockerExecutionEnvelope,
    FormalDrillSequenceDefinition,
    canonical_formal_drill_sequence,
    execute_formal_drill_sequence,
    materialize_formal_signal_envelope,
)
from .drill_formal_cli import (
    FORMAL_FULL_SEQUENCE_ENTRY,
    LEGACY_FORMAL_MUTATION_ENTRY_FAILURE,
    FormalDrillCliConfig,
    build_formal_drill_cli_config,
    execute_canonical_formal_drill,
)
from .drill_docker_runtime import (
    CANONICAL_DOCKER_CLI_ENTRY_PATH,
    CANONICAL_DOCKER_CLI_TARGET_PATH,
    FormalExecutorDockerRuntimeContract,
    canonical_docker_argv,
    validate_canonical_docker_argv,
)
from .drill_images import (
    OBSERVER_BACKEND_IMAGE_ROLE,
    POSTGRES_DRILL_IMAGE_ROLE,
    DisposableDrillImageContract,
    drill_image_digest,
    validate_drill_image_ref,
)
from .drill_observer import (
    DisposableDrillObserverConfig,
    launch_disposable_drill_observer,
)
from .drill_readback import (
    CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS,
    DisposableDrillContainerReadbackContract,
    execute_disposable_container_readback,
)
from .drill_readback_projection import (
    CONTAINER_READBACK_MAX_BYTES,
    CONTAINER_READBACK_ROLES,
    CONTAINER_READBACK_SCHEMA_VERSION,
    container_readback_argv,
    container_readback_projection_format,
    parse_container_readback_projection,
)
from .drill_preconditions import (
    secure_create_precondition,
    secure_precondition_readback,
)
from .drill_names import (
    DISPOSABLE_DRILL_NAME_PATTERN,
    DRILL_SUFFIX_PATTERN,
    canonical_disposable_drill_name,
    normalize_disposable_drill_suffix,
    validate_disposable_drill_name,
)
from .drill_runtime import FormalExecutorPythonRuntimeContract
from .evidence import EvidenceBudget, EvidenceCapacityExhausted, ObserverEvidenceStore
from .events import SignalGenerateEvent, parse_signal_generate_line, read_namespace_pids
from .pgbouncer import PgBouncerCorrelationClient
from .service import ObserverConfig, PostgresSignalObserver
from .tracefs import SIGNAL_FILTER, TraceFsInstance

__all__ = [
    "EvidenceBudget",
    "EvidenceCapacityExhausted",
    "FORMAL_DOCKER_OPERATION_CLASSES",
    "FORMAL_DRILL_CLEANUP_ORDER",
    "FORMAL_DRILL_SEQUENCE_ORDER",
    "FORMAL_DRILL_TERMINAL_COMPLETE",
    "FORMAL_FULL_SEQUENCE_ENTRY",
    "FormalDockerExecutionEnvelope",
    "FormalDrillSequenceDefinition",
    "FormalExecutorDockerRuntimeContract",
    "FormalExecutorPythonRuntimeContract",
    "FormalDrillCliConfig",
    "LEGACY_FORMAL_MUTATION_ENTRY_FAILURE",
    "POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS",
    "DRILL_APPLICATION_NAME",
    "DisposableDrillBootstrapConfig",
    "DisposableDrillClientConfig",
    "DisposableDrillContainerReadbackContract",
    "DisposableDrillImageContract",
    "DisposableDrillSignalConfig",
    "DisposableDrillObserverConfig",
    "DisposableDrillObserverEnvironment",
    "DISPOSABLE_DRILL_NAME_PATTERN",
    "DRILL_SUFFIX_PATTERN",
    "ObserverConfig",
    "OBSERVER_BACKEND_IMAGE_ROLE",
    "ObserverEvidenceStore",
    "PgBouncerCorrelationClient",
    "PGBOUNCER_DECLARED_VOLUME_TMPFS",
    "PGBOUNCER_ADMIN_ENVIRONMENT_KEY",
    "POSTGRES_DATA_TMPFS",
    "POSTGRES_DRILL_IMAGE_ROLE",
    "POSTGRES_BACKEND_PID_MAX",
    "POSTGRES_SIGNAL_NAME",
    "POSTGRES_SIGNAL_OUTPUT_BUDGET_BYTES",
    "POSTGRES_SIGNAL_SENDER_EXECUTABLE",
    "POSTGRES_SIGNAL_SENDER_USER",
    "POSTGRES_SIGNAL_TERMINAL_DEADLINE_SECONDS",
    "CANONICAL_DOCKER_CLI_ENTRY_PATH",
    "CANONICAL_DOCKER_CLI_TARGET_PATH",
    "CONTAINER_READBACK_MAX_BYTES",
    "CONTAINER_READBACK_ROLES",
    "CONTAINER_READBACK_SCHEMA_VERSION",
    "CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS",
    "PostgresSignalObserver",
    "SIGNAL_FILTER",
    "SignalGenerateEvent",
    "TraceFsInstance",
    "canonical_observer_artifact_sha256",
    "canonical_docker_argv",
    "container_readback_argv",
    "container_readback_projection_format",
    "canonical_disposable_drill_name",
    "canonical_disposable_drill_temp_root",
    "drill_image_digest",
    "execute_formal_postgres_bootstrap",
    "canonical_formal_drill_sequence",
    "execute_formal_drill_sequence",
    "materialize_formal_signal_envelope",
    "execute_canonical_formal_drill",
    "build_formal_drill_cli_config",
    "execute_disposable_container_readback",
    "launch_disposable_drill_client",
    "launch_disposable_drill_observer",
    "send_disposable_drill_signal",
    "secure_create_precondition",
    "secure_precondition_readback",
    "parse_signal_generate_line",
    "parse_container_readback_projection",
    "normalize_disposable_drill_suffix",
    "read_namespace_pids",
    "serialize_postgres_bootstrap_environment",
    "serialize_disposable_pgbouncer_config",
    "serialize_disposable_pgbouncer_userlist",
    "validate_formal_exec_result",
    "validate_canonical_docker_argv",
    "validate_disposable_drill_name",
    "validate_drill_image_ref",
]
