"""Single-process event loop for bounded PostgreSQL signal attribution."""

from __future__ import annotations

import hashlib
import os
import re
import select
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services.runtime_database_incident_gate import (
    record_database_failure,
    require_runtime_database_mutation_allowed,
)

from .artifact import canonical_observer_artifact_sha256
from .evidence import EvidenceCapacityExhausted, ObserverEvidenceStore
from .events import parse_signal_generate_line, read_namespace_pids
from .pgbouncer import PgBouncerCorrelationClient
from .tracefs import SIGNAL_FILTER, TraceFsInstance


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_STABLE_OBSERVER_FAILURE_CODES = frozenset(
    {
        "incident_diagnostic_permit_required",
        "observer_artifact_sha256_invalid",
        "observer_artifact_sha256_missing",
        "observer_artifact_sha256_readback_mismatch",
        "observer_image_digest_invalid",
        "observer_image_digest_missing",
        "observer_pgbouncer_admin_url_missing",
        "observer_error_unclassified_config_and_permit_validation",
        "observer_error_unclassified_trace_pipe_runtime",
        "observer_error_unclassified_tracefs_prepare",
        "observer_source_commit_invalid",
        "observer_source_commit_missing",
        "signal_event_correlation_unavailable",
        "trace_pipe_closed",
        "tracefs_control_write_failed",
        "tracefs_filter_readback_mismatch",
        "tracefs_mount_or_signal_event_unavailable",
        "tracefs_trace_pipe_unavailable",
    }
)

_OBSERVER_FAILURE_PHASE_FALLBACKS = {
    "config_and_permit_validation": (
        "observer_error_unclassified_config_and_permit_validation"
    ),
    "tracefs_prepare": "observer_error_unclassified_tracefs_prepare",
    "trace_pipe_runtime": "observer_error_unclassified_trace_pipe_runtime",
}


def canonical_observer_failure_detail_code(
    value: object,
    *,
    phase: str | None = None,
) -> str:
    """Return one exact allowlisted code without serializing error payloads."""

    candidate = str(value)
    if candidate in _STABLE_OBSERVER_FAILURE_CODES:
        return candidate
    if candidate.startswith("tracefs_control_write_failed:"):
        return "tracefs_control_write_failed"
    phase_fallback = _OBSERVER_FAILURE_PHASE_FALLBACKS.get(phase)
    if phase_fallback is not None:
        return phase_fallback
    return "observer_error_unclassified"


@dataclass(frozen=True)
class ObserverConfig:
    evidence_root: Path
    journal_root: Path
    pgbouncer_admin_url: str
    artifact_sha256: str
    source_commit: str
    image_digest: str
    repo_root: Path = Path("/app")
    trace_root: Path = Path("/sys/kernel/tracing")
    heartbeat_seconds: float = 5.0

    @classmethod
    def from_environment(cls) -> "ObserverConfig":
        return cls(
            evidence_root=Path(
                os.getenv(
                    "POSTGRES_SIGNAL_OBSERVER_EVIDENCE_DIR",
                    "/app/data/runtime-database-incidents/signal-observer",
                )
            ),
            journal_root=Path(
                os.getenv(
                    "RUNTIME_DATABASE_INCIDENT_DIR",
                    "/app/data/runtime-database-incidents",
                )
            ),
            pgbouncer_admin_url=os.getenv("PGBOUNCER_ADMIN_URL", ""),
            artifact_sha256=os.getenv("POSTGRES_SIGNAL_OBSERVER_ARTIFACT_SHA256", ""),
            source_commit=os.getenv("POSTGRES_SIGNAL_OBSERVER_SOURCE_COMMIT", ""),
            image_digest=os.getenv("POSTGRES_SIGNAL_OBSERVER_IMAGE_DIGEST", ""),
            repo_root=Path(
                os.getenv(
                    "POSTGRES_SIGNAL_OBSERVER_REPO_ROOT",
                    str(Path(__file__).resolve().parents[3]),
                )
            ),
            trace_root=Path(
                os.getenv("POSTGRES_SIGNAL_OBSERVER_TRACE_ROOT", "/sys/kernel/tracing")
            ),
        )

    def validate(self) -> None:
        for name, value in {
            "artifact_sha256": self.artifact_sha256,
            "source_commit": self.source_commit,
            "image_digest": self.image_digest,
        }.items():
            if not str(value).strip():
                raise ValueError(f"observer_{name}_missing")
        if len(self.artifact_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.artifact_sha256
        ):
            raise ValueError("observer_artifact_sha256_invalid")
        if not re.fullmatch(r"[0-9a-f]{8,64}", self.source_commit):
            raise ValueError("observer_source_commit_invalid")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_digest):
            raise ValueError("observer_image_digest_invalid")
        if not self.pgbouncer_admin_url:
            raise ValueError("observer_pgbouncer_admin_url_missing")
        actual_artifact_sha256 = canonical_observer_artifact_sha256(self.repo_root)
        if actual_artifact_sha256 != self.artifact_sha256:
            raise ValueError("observer_artifact_sha256_readback_mismatch")


class PostgresSignalObserver:
    """Observe only filtered SIGQUIT events and append immutable references."""

    def __init__(
        self,
        config: ObserverConfig,
        *,
        store: ObserverEvidenceStore | None = None,
        trace: TraceFsInstance | None = None,
        correlation: PgBouncerCorrelationClient | None = None,
    ) -> None:
        self.config = config
        self.store = store or ObserverEvidenceStore(config.evidence_root)
        self.trace = trace or TraceFsInstance(config.trace_root)
        self.correlation = correlation or PgBouncerCorrelationClient(
            config.pgbouncer_admin_url
        )
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True

    def _health(self, *, ready: bool, state: str, **details: Any) -> dict[str, Any]:
        return self.store.write_health(
            {
                "ready": ready,
                "state": state,
                "filter": SIGNAL_FILTER,
                "filter_sha256": hashlib.sha256(
                    SIGNAL_FILTER.encode("utf-8")
                ).hexdigest(),
                "source_commit": self.config.source_commit,
                "image_digest": self.config.image_digest,
                "artifact_sha256": self.config.artifact_sha256,
                "heartbeat_at": utc_now(),
                **details,
            }
        )

    def _process_line(self, line: str) -> None:
        event = parse_signal_generate_line(line)
        if event is None:
            return
        correlation_error = ""
        try:
            target_namespace_pids = read_namespace_pids(event.target_host_pid)
            target_postgres_pid = target_namespace_pids[-1]
        except Exception as exc:
            target_namespace_pids = ()
            target_postgres_pid = 0
            correlation_error = type(exc).__name__
        try:
            sender_namespace_pids = read_namespace_pids(event.sender_host_pid)
        except Exception:
            sender_namespace_pids = ()
        if target_postgres_pid:
            try:
                correlation = self.correlation.correlate(target_postgres_pid)
            except Exception as exc:
                correlation = {
                    "status": "correlation_unavailable",
                    "error_code": type(exc).__name__,
                }
                correlation_error = type(exc).__name__
        else:
            correlation = {
                "status": "correlation_unavailable",
                "error_code": correlation_error or "target_namespace_pid_unavailable",
            }
        payload = {
            "observed_at": utc_now(),
            "signal": event.to_dict(),
            "sender_namespace_pids": list(sender_namespace_pids),
            "target_namespace_pids": list(target_namespace_pids),
            "target_postgres_pid": target_postgres_pid,
            "pgbouncer": correlation,
            "filter": SIGNAL_FILTER,
        }
        receipt = self.store.append_event(payload)
        record_database_failure(
            "postgres_sigquit_signal_observed",
            evidence={
                "sender_comm": event.sender_comm,
                "sender_host_pid": str(event.sender_host_pid),
                "target_host_pid": str(event.target_host_pid),
                "target_postgres_pid": str(target_postgres_pid),
                "application_name": str(correlation.get("application_name") or ""),
                "client_process_pid": str(correlation.get("client_remote_pid") or 0),
                "signal_event_path": receipt["event_path"],
                "signal_event_sha256": receipt["event_sha256"],
            },
            journal_root=self.config.journal_root,
        )
        if correlation.get("status") != "correlated":
            raise RuntimeError("signal_event_correlation_unavailable")

    def run(self) -> int:
        failure_phase = "config_and_permit_validation"
        try:
            # Persist a bounded startup receipt before any tracefs operation.  The
            # launcher can then distinguish an observer that is still starting
            # from an inherited or missing container healthcheck, and enforce
            # its fixed startup deadline without querying PostgreSQL/PgBouncer.
            self._health(
                ready=False,
                state="starting",
                startup_phase="config_and_permit_validation",
            )
            self.config.validate()
            decision = require_runtime_database_mutation_allowed(
                "postgres_signal_observer_start",
                evidence={"artifact_sha256": self.config.artifact_sha256},
                journal_root=self.config.journal_root,
            )
            if decision.reason != "incident_diagnostic_permit":
                raise RuntimeError("incident_diagnostic_permit_required")
            failure_phase = "tracefs_prepare"
            self._health(
                ready=False,
                state="starting",
                startup_phase="tracefs_prepare",
            )
            actual_filter = self.trace.prepare()
            self._health(
                ready=True,
                state="ready",
                trace_instance=self.trace.instance_name,
                filter_readback=actual_filter,
                pgbouncer_correlation_ready=True,
            )
            failure_phase = "trace_pipe_runtime"
            with self.trace.open_pipe() as trace_pipe:
                while not self._stopping:
                    readable, _, _ = select.select(
                        [trace_pipe], [], [], self.config.heartbeat_seconds
                    )
                    if not readable:
                        self._health(
                            ready=True,
                            state="ready",
                            trace_instance=self.trace.instance_name,
                            filter_readback=actual_filter,
                            pgbouncer_correlation_ready=True,
                        )
                        continue
                    line = trace_pipe.readline()
                    if not line:
                        raise RuntimeError("trace_pipe_closed")
                    self._process_line(line)
                    self._health(
                        ready=True,
                        state="ready",
                        trace_instance=self.trace.instance_name,
                        filter_readback=actual_filter,
                        pgbouncer_correlation_ready=True,
                    )
            return 0
        except EvidenceCapacityExhausted as exc:
            self._health(
                ready=False,
                state="fail_closed_capacity_exhausted",
                error_code=str(exc),
            )
            return 2
        except Exception as exc:
            self._health(
                ready=False,
                state="fail_closed_observer_error",
                error_code=type(exc).__name__,
                error_class=type(exc).__name__,
                failure_detail_code=canonical_observer_failure_detail_code(
                    exc,
                    phase=failure_phase,
                ),
            )
            return 2
        finally:
            self.trace.cleanup()
