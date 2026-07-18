"""Single invocation owner for the formal isolated observer drill sequence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .drill import DisposableDrillClientConfig, DisposableDrillSignalConfig
from .drill_bootstrap import DisposableDrillBootstrapConfig
from .drill_docker_runtime import validate_canonical_docker_argv
from .drill_escalation import (
    FORMAL_DOCKER_OPERATION_RESULT_KINDS,
    validate_formal_exec_result,
)
from .drill_gate_receipt import project_formal_gate_receipt
from .drill_observer import DisposableDrillObserverConfig


FORMAL_DRILL_TERMINAL_COMPLETE = "formal_drill_sequence_terminal_complete"
FORMAL_DRILL_GATE_FAILURES = {
    "postgres_readiness": "formal_postgres_readiness_failed",
    "pgbouncer_readiness": "formal_pgbouncer_readiness_failed",
    "observer_health": "formal_observer_health_failed",
    "client_ready": "formal_client_ready_failed",
    "sender_target_correlation": "formal_sender_target_correlation_failed",
}
FORMAL_DRILL_SEQUENCE_ORDER = (
    "network_create",
    "postgres_bootstrap",
    "postgres_readiness",
    "pgbouncer_bootstrap",
    "pgbouncer_readiness",
    "observer_launch",
    "observer_health",
    "client_launch",
    "client_ready",
    "signal_send",
    "sender_target_correlation",
)
FORMAL_DRILL_CLEANUP_ORDER = (
    "client_stop",
    "client_remove",
    "observer_stop",
    "observer_remove",
    "pgbouncer_stop",
    "pgbouncer_remove",
    "postgres_stop",
    "postgres_remove",
    "network_remove",
)


@dataclass(frozen=True)
class FormalDockerExecutionEnvelope:
    """One receipt-visible Docker operation owned by the formal executor."""

    operation_class: str
    argv: tuple[str, ...]
    terminal_failure_code: str
    result_kind: str
    resource: str | None = None

    def validate(self) -> None:
        expected = FORMAL_DOCKER_OPERATION_RESULT_KINDS.get(self.operation_class)
        if expected is None or self.result_kind != expected:
            raise ValueError("formal_escalation_operation_class_invalid")
        if not re.fullmatch(r"[a-z0-9_]{3,160}", self.terminal_failure_code):
            raise ValueError("formal_escalation_terminal_failure_code_invalid")
        if self.resource not in {None, "network", "postgres", "pgbouncer", "observer", "client"}:
            raise ValueError("formal_escalation_resource_invalid")
        try:
            validate_canonical_docker_argv(self.argv)
        except ValueError as exc:
            raise ValueError("formal_escalation_docker_argv_invalid") from exc

    def redacted_spec(self) -> dict[str, Any]:
        self.validate()
        return {
            "operation_class": self.operation_class,
            "result_kind": self.result_kind,
            "terminal_failure_code": self.terminal_failure_code,
            "resource": self.resource,
            "argv": list(self.argv),
            "argv_sha256": hashlib.sha256(
                "\0".join(self.argv).encode("utf-8")
            ).hexdigest(),
            "requires_formal_escalation": True,
            "sandbox_docker_execution_allowed": False,
            "shell": False,
            "fallback": False,
            "second_launcher": False,
        }


@dataclass(frozen=True)
class FormalDrillSequenceStep:
    name: str
    envelope: FormalDockerExecutionEnvelope | None = None
    dynamic_operation: str | None = None

    @property
    def kind(self) -> str:
        if self.envelope is not None:
            return "docker"
        if self.dynamic_operation is not None:
            return "source_owned_dynamic_docker"
        return "gate"


@dataclass(frozen=True)
class FormalDrillSequenceDefinition:
    steps: tuple[FormalDrillSequenceStep, ...]
    cleanup_envelopes: tuple[FormalDockerExecutionEnvelope, ...]

    def validate(self) -> None:
        if tuple(step.name for step in self.steps) != FORMAL_DRILL_SEQUENCE_ORDER:
            raise ValueError("formal_drill_sequence_order_invalid")
        if tuple(
            _cleanup_name(envelope.operation_class)
            for envelope in self.cleanup_envelopes
        ) != FORMAL_DRILL_CLEANUP_ORDER:
            raise ValueError("formal_drill_cleanup_order_invalid")
        for step in self.steps:
            if step.envelope is not None:
                if step.dynamic_operation is not None:
                    raise ValueError("formal_drill_step_operation_ambiguous")
                step.envelope.validate()
            elif step.dynamic_operation is not None:
                if step.dynamic_operation != "source_owned_signal_sender":
                    raise ValueError("formal_drill_dynamic_operation_invalid")
            elif step.name not in FORMAL_DRILL_GATE_FAILURES:
                raise ValueError("formal_drill_gate_invalid")
        for envelope in self.cleanup_envelopes:
            envelope.validate()

    def redacted_spec(self) -> dict[str, Any]:
        self.validate()
        return {
            "entry": "postgres_signal_observer_drill.execute_formal_drill_sequence",
            "sequence": [
                {
                    "name": step.name,
                    "kind": step.kind,
                    "operation": (
                        step.envelope.redacted_spec()
                        if step.envelope is not None
                        else (
                            {
                                "source_owned_late_bound": True,
                                "owner": step.dynamic_operation,
                                "external_target_pid_allowed": False,
                            }
                            if step.dynamic_operation is not None
                            else None
                        )
                    ),
                }
                for step in self.steps
            ],
            "cleanup": [item.redacted_spec() for item in self.cleanup_envelopes],
            "invocation_local_first_failure_latch": True,
            "permit_revoked_on_every_terminal_path": True,
            "correlation_required_for_validation": True,
            "manual_formal_mutation_steps_allowed": False,
        }


def _cleanup_name(operation_class: str) -> str:
    match = re.fullmatch(
        r"docker_(stop|remove)_disposable_isolated_"
        r"(client|observer|pgbouncer|postgresql|network)",
        operation_class,
    )
    if match is None:
        return ""
    action, resource = match.groups()
    normalized_resource = "postgres" if resource == "postgresql" else resource
    return f"{normalized_resource}_{action}"


def _envelope(
    operation_class: str,
    argv: tuple[str, ...],
    failure: str,
    *,
    result_kind: str,
    resource: str | None,
) -> FormalDockerExecutionEnvelope:
    envelope = FormalDockerExecutionEnvelope(
        operation_class=operation_class,
        argv=argv,
        terminal_failure_code=failure,
        result_kind=result_kind,
        resource=resource,
    )
    envelope.validate()
    return envelope


def canonical_formal_drill_sequence(
    bootstrap: DisposableDrillBootstrapConfig,
    observer: DisposableDrillObserverConfig,
    client: DisposableDrillClientConfig,
) -> FormalDrillSequenceDefinition:
    """Build the one exact full sequence; callers never assemble Docker argv."""

    if (
        observer.container_name != bootstrap.observer_container_name
        or observer.pgbouncer_container_name != bootstrap.pgbouncer_container_name
        or client.container_name != bootstrap.client_container_name
        or client.network_name != bootstrap.network_name
        or client.pgbouncer_host != bootstrap.pgbouncer_container_name
    ):
        raise ValueError("formal_drill_sequence_identity_mismatch")
    lifecycle = bootstrap.lifecycle_docker_argv()
    steps = (
        FormalDrillSequenceStep(
            "network_create",
            _envelope(
                "docker_create_disposable_isolated_network",
                lifecycle["network_create"],
                "formal_isolated_network_create_terminal_failure",
                result_kind="identifier",
                resource="network",
            ),
        ),
        FormalDrillSequenceStep(
            "postgres_bootstrap",
            _envelope(
                "docker_run_disposable_isolated_postgresql_bootstrap",
                bootstrap.postgres_docker_argv(),
                "formal_postgres_bootstrap_terminal_failure",
                result_kind="identifier",
                resource="postgres",
            ),
        ),
        FormalDrillSequenceStep("postgres_readiness"),
        FormalDrillSequenceStep(
            "pgbouncer_bootstrap",
            _envelope(
                "docker_run_disposable_isolated_pgbouncer_bootstrap",
                bootstrap.pgbouncer_docker_argv(),
                "formal_pgbouncer_bootstrap_terminal_failure",
                result_kind="identifier",
                resource="pgbouncer",
            ),
        ),
        FormalDrillSequenceStep("pgbouncer_readiness"),
        FormalDrillSequenceStep(
            "observer_launch",
            _envelope(
                "docker_run_disposable_isolated_observer",
                observer.docker_argv(),
                "formal_observer_launch_terminal_failure",
                result_kind="identifier",
                resource="observer",
            ),
        ),
        FormalDrillSequenceStep("observer_health"),
        FormalDrillSequenceStep(
            "client_launch",
            _envelope(
                "docker_run_disposable_isolated_client",
                client.docker_argv(),
                "formal_client_launch_terminal_failure",
                result_kind="identifier",
                resource="client",
            ),
        ),
        FormalDrillSequenceStep("client_ready"),
        FormalDrillSequenceStep(
            "signal_send",
            dynamic_operation="source_owned_signal_sender",
        ),
        FormalDrillSequenceStep("sender_target_correlation"),
    )
    cleanup_envelopes = tuple(
        _envelope(
            operation_class,
            lifecycle[lifecycle_name],
            f"{operation_class}_terminal_failure",
            result_kind="terminal_zero",
            resource=resource,
        )
        for operation_class, lifecycle_name, resource in (
            ("docker_stop_disposable_isolated_client", "client_stop", "client"),
            ("docker_remove_disposable_isolated_client", "client_remove", "client"),
            ("docker_stop_disposable_isolated_observer", "observer_stop", "observer"),
            ("docker_remove_disposable_isolated_observer", "observer_remove", "observer"),
            ("docker_stop_disposable_isolated_pgbouncer", "pgbouncer_stop", "pgbouncer"),
            ("docker_remove_disposable_isolated_pgbouncer", "pgbouncer_remove", "pgbouncer"),
            ("docker_stop_disposable_isolated_postgresql", "postgres_stop", "postgres"),
            ("docker_remove_disposable_isolated_postgresql", "postgres_remove", "postgres"),
            ("docker_remove_disposable_isolated_network", "network_remove", "network"),
        )
    )
    definition = FormalDrillSequenceDefinition(steps, cleanup_envelopes)
    definition.validate()
    return definition


def materialize_formal_signal_envelope(
    signal: DisposableDrillSignalConfig,
) -> FormalDockerExecutionEnvelope:
    """Bind the source-owned active-session PID to the exact executed argv."""

    return _envelope(
        "docker_exec_disposable_isolated_signal_sender",
        signal.docker_argv(),
        "formal_signal_sender_terminal_failure",
        result_kind="terminal_zero",
        resource=None,
    )


def execute_formal_drill_sequence(
    definition: FormalDrillSequenceDefinition,
    *,
    execute_docker: Callable[[FormalDockerExecutionEnvelope], Mapping[str, Any]],
    evaluate_gate: Callable[[str], Mapping[str, Any]],
    materialize_operation: Callable[[str], FormalDockerExecutionEnvelope],
    revoke_permit: Callable[[str], Any],
    finalize_cleanup: Callable[[str | None], Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute one full sequence with one first-failure latch and terminal handback."""

    definition.validate()
    attempted_steps: list[str] = []
    step_receipts: list[dict[str, Any]] = []
    created_resources: set[str] = set()
    first_failure: str | None = None

    for step in definition.steps:
        attempted_steps.append(step.name)
        if step.envelope is None and step.dynamic_operation is None:
            try:
                gate = evaluate_gate(step.name)
            except Exception:
                gate = {}
            projected_gate = project_formal_gate_receipt(step.name, gate)
            passed = projected_gate.get("passed") is True
            step_receipts.append(projected_gate)
            if not passed:
                first_failure = FORMAL_DRILL_GATE_FAILURES[step.name]
                break
            continue
        envelope = step.envelope
        if envelope is None:
            try:
                envelope = materialize_operation(str(step.dynamic_operation))
                envelope.validate()
            except Exception:
                first_failure = "formal_signal_target_pid_not_source_owned"
                step_receipts.append(
                    {
                        "name": step.name,
                        "kind": "source_owned_dynamic_docker",
                        "materialized": False,
                    }
                )
                break
        try:
            source = execute_docker(envelope)
        except Exception:
            source = {"exit_code": 1, "output": ""}
        result = validate_formal_exec_result(
            source,
            operation_class=envelope.operation_class,
        )
        step_receipts.append(
            {
                "name": step.name,
                "kind": "formal_operation",
                "operation": envelope.redacted_spec(),
                "result": result,
            }
        )
        resource_may_exist = bool(
            envelope.resource is not None
            and isinstance(source, Mapping)
            and (
                source.get("resource_may_exist") is True
                or source.get("exit_code") == 0
            )
        )
        if resource_may_exist and envelope.resource is not None:
            created_resources.add(envelope.resource)
        if result.get("delivery_allowed") is not True:
            candidate = source.get("failure_code") if isinstance(source, Mapping) else None
            first_failure = (
                candidate
                if isinstance(candidate, str) and re.fullmatch(r"[a-z0-9_]{3,160}", candidate)
                else envelope.terminal_failure_code
            )
            break
        if envelope.resource is not None:
            created_resources.add(envelope.resource)

    terminal_reason = first_failure or FORMAL_DRILL_TERMINAL_COMPLETE
    revocation_completed = False
    revocation_error: str | None = None
    try:
        revoke_permit(terminal_reason)
    except Exception:
        revocation_error = "permit_revocation_failed"
    else:
        revocation_completed = True

    cleanup_receipts: list[dict[str, Any]] = []
    cleanup_failures: list[str] = []
    for envelope in definition.cleanup_envelopes:
        if envelope.resource not in created_resources:
            continue
        try:
            source = execute_docker(envelope)
        except Exception:
            source = {"exit_code": 1, "output": ""}
        result = validate_formal_exec_result(
            source,
            operation_class=envelope.operation_class,
        )
        cleanup_receipts.append(result)
        if result.get("delivery_allowed") is not True:
            cleanup_failures.append(envelope.terminal_failure_code)

    finalize_error: str | None = None
    try:
        postflight = finalize_cleanup(first_failure)
    except Exception:
        postflight = {}
        finalize_error = "cleanup_postflight_failed"
    remaining_verified = (
        isinstance(postflight, Mapping)
        and postflight.get("remaining_resources_verified") is True
    )
    reported_owner = postflight.get("terminal_owner") if isinstance(postflight, Mapping) else None
    reported_handback = (
        isinstance(postflight, Mapping) and postflight.get("handed_back") is True
    )
    cleanup_completed = not cleanup_failures and finalize_error is None and remaining_verified
    ownership_handed_back = (
        revocation_completed
        and cleanup_completed
        and reported_owner == "none"
        and reported_handback
    )
    correlation_passed = "sender_target_correlation" in attempted_steps and (
        first_failure is None
    )
    validation_passed = (
        first_failure is None
        and correlation_passed
        and revocation_completed
        and cleanup_completed
        and ownership_handed_back
    )
    terminal_owner = "none" if ownership_handed_back else (
        reported_owner if isinstance(reported_owner, str) and reported_owner != "none" else "unknown"
    )
    docker_attempts = [
        step.name
        for step in definition.steps[: len(attempted_steps)]
        if step.envelope is not None or step.dynamic_operation is not None
    ]
    return {
        "validation_passed": validation_passed,
        "first_failure": first_failure,
        "first_failure_latched": first_failure is not None,
        "attempted_steps": attempted_steps,
        "blocked_steps": list(FORMAL_DRILL_SEQUENCE_ORDER[len(attempted_steps) :]),
        "step_receipts": step_receipts,
        "docker_operation_attempts": docker_attempts,
        "downstream_operation_attempts": {
            role: sum(role in name for name in docker_attempts)
            for role in ("postgres", "pgbouncer", "observer", "client", "signal")
        },
        "same_permit_downstream_mutation_attempt": False,
        "correlation_passed": correlation_passed,
        "permit_revocation_required": True,
        "permit_revocation_completed": revocation_completed,
        "permit_revocation_failure_code": first_failure,
        "permit_revocation_terminal_reason": terminal_reason,
        "permit_revocation_error": revocation_error,
        "cleanup_operation_attempts": len(cleanup_receipts),
        "cleanup_operation_receipts": cleanup_receipts,
        "cleanup_failures": cleanup_failures,
        "cleanup_completed": cleanup_completed,
        "finalize_cleanup_error": finalize_error,
        "remaining_resources_verified": remaining_verified,
        "terminal_owner": terminal_owner,
        "ownership_handed_back": ownership_handed_back,
        "formal_executor": definition.redacted_spec(),
    }
