#!/usr/bin/env python3
"""Facade for the permit-gated disposable signal-observer drill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.runtime_database_incident_gate import (  # noqa: E402
    require_runtime_database_mutation_allowed,
)
from scripts.maintenance.postgres_signal_observer_core import (  # noqa: E402
    DisposableDrillBootstrapConfig,
    DisposableDrillClientConfig,
    DisposableDrillImageContract,
    DisposableDrillObserverConfig,
    DisposableDrillSignalConfig,
    OBSERVER_BACKEND_IMAGE_ROLE,
    POSTGRES_DRILL_IMAGE_ROLE,
    canonical_disposable_drill_name,
    canonical_observer_artifact_sha256,
    execute_formal_postgres_bootstrap,
    launch_disposable_drill_client,
    launch_disposable_drill_observer,
    send_disposable_drill_signal,
    serialize_postgres_bootstrap_environment,
    validate_formal_exec_result,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print-client-spec", action="store_true")
    mode.add_argument("--launch-client", action="store_true")
    mode.add_argument("--print-observer-spec", action="store_true")
    mode.add_argument("--launch-observer", action="store_true")
    mode.add_argument("--print-bootstrap-spec", action="store_true")
    mode.add_argument("--prepare-bootstrap-preconditions", action="store_true")
    mode.add_argument("--execute-postgres-bootstrap", action="store_true")
    mode.add_argument("--validate-pgbouncer-readback", type=Path)
    mode.add_argument("--validate-formal-exec-result", type=Path)
    mode.add_argument("--print-signal-spec", action="store_true")
    mode.add_argument("--send-synthetic-signal", action="store_true")
    parser.add_argument("--journal-root", type=Path)
    parser.add_argument("--drill-suffix")
    parser.add_argument("--temp-root", type=Path)
    parser.add_argument("--postgres-drill-image-ref", required=True)
    parser.add_argument("--observer-backend-image-ref", required=True)
    parser.add_argument("--formal-operation-class")
    parser.add_argument("--pgbouncer-port", type=int, default=6432)
    parser.add_argument("--database-user")
    parser.add_argument("--database-name")
    parser.add_argument("--source-commit")
    parser.add_argument("--sleep-seconds", type=int, default=120)
    parser.add_argument("--target-postgres-pid", type=int)
    return parser


def _required(value: object, option: str) -> object:
    if value is None or not str(value).strip():
        raise SystemExit(f"{option} is required for the selected mode")
    return value


def _with_image_contract(
    payload: dict[str, object],
    *,
    image_contract: DisposableDrillImageContract,
    selected_role: str,
) -> dict[str, object]:
    """Bind every facade receipt to both validated image owners."""

    return {
        **payload,
        "selected_image_role": selected_role,
        "image_contract": image_contract.redacted_spec(),
    }


def _secure_create_precondition(path: Path, content: bytes) -> None:
    """Create one exclusive 0600 regular file without following symlinks."""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(nofollow, int):
        raise RuntimeError("drill_precondition_nofollow_unavailable")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow
    cloexec = getattr(os, "O_CLOEXEC", None)
    if isinstance(cloexec, int):
        flags |= cloexec
    descriptor = os.open(path, flags, 0o600)
    try:
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise RuntimeError("drill_precondition_file_contract_invalid")
            view = memoryview(content)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise RuntimeError("drill_precondition_write_incomplete")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _secure_precondition_readback(path: Path) -> dict[str, object]:
    """Read one staged precondition through a verified no-follow fd."""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(nofollow, int):
        raise RuntimeError("drill_precondition_nofollow_unavailable")
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError("drill_precondition_file_contract_invalid")
    flags = os.O_RDONLY | nofollow
    cloexec = getattr(os, "O_CLOEXEC", None)
    if isinstance(cloexec, int):
        flags |= cloexec
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or (metadata.st_dev, metadata.st_ino) != (before.st_dev, before.st_ino)
            or metadata.st_size > 65_536
        ):
            raise RuntimeError("drill_precondition_file_contract_invalid")
        chunks: list[bytes] = []
        remaining = 65_537
        while remaining > 0:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > 65_536:
            raise RuntimeError("drill_precondition_file_contract_invalid")
    finally:
        os.close(descriptor)
    return {
        "path": str(path),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "regular_file": True,
        "symlink": False,
        "content_or_value_disclosed": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    image_contract = DisposableDrillImageContract(
        postgres_image_ref=args.postgres_drill_image_ref,
        observer_image_ref=args.observer_backend_image_ref,
    )
    try:
        image_contract.validate()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    artifact_sha256 = canonical_observer_artifact_sha256(REPO_ROOT)
    if args.validate_formal_exec_result:
        result_path = Path(args.validate_formal_exec_result)
        if result_path.is_symlink() or not result_path.is_file():
            raise SystemExit("--validate-formal-exec-result must be a regular file")
        try:
            source = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit("formal exec result is unavailable or invalid") from exc
        if not isinstance(source, dict):
            raise SystemExit("formal exec result must be a JSON object")
        payload = validate_formal_exec_result(
            source,
            operation_class=str(
                _required(args.formal_operation_class, "--formal-operation-class")
            ),
        )
        payload["artifact_sha256"] = artifact_sha256
        payload = _with_image_contract(
            payload,
            image_contract=image_contract,
            selected_role=POSTGRES_DRILL_IMAGE_ROLE,
        )
        print(json.dumps(payload, sort_keys=True))
        if payload.get("delivery_allowed") is True:
            return 0
        return 3 if payload.get("poll_required") is True else 2
    if (
        args.print_bootstrap_spec
        or args.prepare_bootstrap_preconditions
        or args.execute_postgres_bootstrap
        or args.validate_pgbouncer_readback
    ):
        bootstrap_config = DisposableDrillBootstrapConfig(
            drill_suffix=str(_required(args.drill_suffix, "--drill-suffix")),
            temp_root=Path(_required(args.temp_root, "--temp-root")),
            postgres_image_ref=image_contract.image_ref_for(
                POSTGRES_DRILL_IMAGE_ROLE
            ),
        )
        if args.print_bootstrap_spec:
            payload = bootstrap_config.redacted_spec()
            payload["artifact_sha256"] = artifact_sha256
            payload = _with_image_contract(
                payload,
                image_contract=image_contract,
                selected_role=POSTGRES_DRILL_IMAGE_ROLE,
            )
            print(json.dumps(payload, sort_keys=True))
            return 0
        if args.prepare_bootstrap_preconditions:
            paths = (
                bootstrap_config.postgres_environment_path,
                bootstrap_config.pgbouncer_config_path,
                bootstrap_config.pgbouncer_userlist_path,
            )
            if any(path.exists() or path.is_symlink() for path in paths):
                raise RuntimeError("drill_precondition_path_already_exists")
            password = secrets.token_hex(16)
            assignments = {
                "POSTGRES_USER": "mindscape",
                "POSTGRES_PASSWORD": password,
                "POSTGRES_DB": "mindscape_core",
            }
            environment_payload = serialize_postgres_bootstrap_environment(assignments)
            payloads = (
                environment_payload,
                (
                    "[databases]\n"
                    "mindscape_core = host=runtime-db-observer-drill-postgres "
                    "port=5432 dbname=mindscape_core user=mindscape "
                    f"password={password}\n\n"
                    "[pgbouncer]\n"
                    "listen_addr = 0.0.0.0\nlisten_port = 6432\n"
                    "auth_type = plain\n"
                    "auth_file = /etc/pgbouncer/userlist.txt\n"
                    "pool_mode = session\nmax_client_conn = 8\n"
                    "default_pool_size = 2\nmin_pool_size = 0\n"
                    "reserve_pool_size = 0\n"
                    "server_reset_query = DISCARD ALL\n"
                    "ignore_startup_parameters = extra_float_digits\n"
                ).encode("utf-8"),
                f'"mindscape" "{password}"\n'.encode("utf-8"),
            )
            created: list[Path] = []
            try:
                for path, content in zip(paths, payloads, strict=True):
                    _secure_create_precondition(path, content)
                    created.append(path)
                file_receipts = [_secure_precondition_readback(path) for path in paths]
                payload = _with_image_contract(
                    {
                        "artifact_sha256": artifact_sha256,
                        "validation_passed": True,
                        "first_failure": None,
                        "serializer": ("serialize_postgres_bootstrap_environment"),
                        "serializer_invocation": "one_exact_mapping",
                        "materialization": "o_excl_fail_closed_staged_creation",
                        "files": file_receipts,
                        "secret_values_in_argv_or_receipt": False,
                        "shell": False,
                    },
                    image_contract=image_contract,
                    selected_role=POSTGRES_DRILL_IMAGE_ROLE,
                )
                print(json.dumps(payload, sort_keys=True))
            except BaseException:
                for path in reversed(created):
                    path.unlink(missing_ok=True)
                raise
            return 0
        if args.execute_postgres_bootstrap:
            return execute_formal_postgres_bootstrap(
                bootstrap_config.postgres_docker_argv(),
                environment_path=bootstrap_config.postgres_environment_path,
            )
        readback_path = Path(args.validate_pgbouncer_readback)
        if readback_path.is_symlink() or not readback_path.is_file():
            raise SystemExit("--validate-pgbouncer-readback must be a regular file")
        try:
            readback = json.loads(readback_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit("pgbouncer readback is unavailable or invalid") from exc
        payload = bootstrap_config.validate_pgbouncer_readback(readback)
        payload["artifact_sha256"] = artifact_sha256
        payload = _with_image_contract(
            payload,
            image_contract=image_contract,
            selected_role=POSTGRES_DRILL_IMAGE_ROLE,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("validation_passed") is True else 2
    if args.print_signal_spec or args.send_synthetic_signal:
        signal_config = DisposableDrillSignalConfig(
            drill_suffix=str(_required(args.drill_suffix, "--drill-suffix")),
            postgres_image_ref=image_contract.image_ref_for(
                POSTGRES_DRILL_IMAGE_ROLE
            ),
            target_postgres_pid=int(
                _required(args.target_postgres_pid, "--target-postgres-pid")
            ),
        )
        if args.print_signal_spec:
            payload = signal_config.redacted_spec()
            payload["artifact_sha256"] = artifact_sha256
            payload = _with_image_contract(
                payload,
                image_contract=image_contract,
                selected_role=POSTGRES_DRILL_IMAGE_ROLE,
            )
            print(json.dumps(payload, sort_keys=True))
            return 0
        if args.journal_root is None:
            raise SystemExit("--journal-root is required with --send-synthetic-signal")
        decision = require_runtime_database_mutation_allowed(
            "postgres_signal_observer_start",
            evidence={
                "artifact_sha256": artifact_sha256,
                "signal_spec_sha256": signal_config.redacted_spec()["argv_sha256"],
            },
            journal_root=args.journal_root,
        )
        if decision.reason != "incident_diagnostic_permit":
            raise RuntimeError("incident_diagnostic_permit_required")
        receipt = send_disposable_drill_signal(signal_config)
        receipt["artifact_sha256"] = artifact_sha256
        receipt["incident_id"] = decision.incident_id
        receipt["admission_reason"] = decision.reason
        receipt = _with_image_contract(
            receipt,
            image_contract=image_contract,
            selected_role=POSTGRES_DRILL_IMAGE_ROLE,
        )
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt.get("signal_sent") is True else 2
    if args.print_observer_spec or args.launch_observer:
        if args.journal_root is None:
            raise SystemExit("--journal-root is required for observer modes")
        drill_suffix = str(_required(args.drill_suffix, "--drill-suffix"))
        observer_config = DisposableDrillObserverConfig(
            container_name=canonical_disposable_drill_name("observer", drill_suffix),
            pgbouncer_container_name=canonical_disposable_drill_name(
                "pgbouncer", drill_suffix
            ),
            observer_image_ref=image_contract.image_ref_for(
                OBSERVER_BACKEND_IMAGE_ROLE
            ),
            journal_host_root=args.journal_root,
            repo_root=REPO_ROOT,
            artifact_sha256=artifact_sha256,
            source_commit=str(_required(args.source_commit, "--source-commit")),
        )
        if args.print_observer_spec:
            payload = _with_image_contract(
                observer_config.redacted_spec(),
                image_contract=image_contract,
                selected_role=OBSERVER_BACKEND_IMAGE_ROLE,
            )
            print(json.dumps(payload, sort_keys=True))
            return 0
        decision = require_runtime_database_mutation_allowed(
            "postgres_signal_observer_start",
            evidence={"artifact_sha256": artifact_sha256},
            journal_root=args.journal_root,
        )
        if decision.reason != "incident_diagnostic_permit":
            raise RuntimeError("incident_diagnostic_permit_required")
        receipt = launch_disposable_drill_observer(observer_config)
        receipt["artifact_sha256"] = artifact_sha256
        receipt["incident_id"] = decision.incident_id
        receipt["admission_reason"] = decision.reason
        receipt = _with_image_contract(
            receipt,
            image_contract=image_contract,
            selected_role=OBSERVER_BACKEND_IMAGE_ROLE,
        )
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt.get("ready") is True else 2

    drill_suffix = str(_required(args.drill_suffix, "--drill-suffix"))
    config = DisposableDrillClientConfig(
        container_name=canonical_disposable_drill_name("client", drill_suffix),
        network_name=canonical_disposable_drill_name("network", drill_suffix),
        postgres_image_ref=image_contract.image_ref_for(POSTGRES_DRILL_IMAGE_ROLE),
        pgbouncer_host=canonical_disposable_drill_name("pgbouncer", drill_suffix),
        pgbouncer_port=args.pgbouncer_port,
        database_user=str(_required(args.database_user, "--database-user")),
        database_name=str(_required(args.database_name, "--database-name")),
        sleep_seconds=args.sleep_seconds,
    )
    if args.print_client_spec:
        payload = _with_image_contract(
            config.redacted_spec(),
            image_contract=image_contract,
            selected_role=POSTGRES_DRILL_IMAGE_ROLE,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.journal_root is None:
        raise SystemExit("--journal-root is required with --launch-client")
    decision = require_runtime_database_mutation_allowed(
        "postgres_signal_observer_start",
        evidence={"artifact_sha256": artifact_sha256},
        journal_root=args.journal_root,
    )
    if decision.reason != "incident_diagnostic_permit":
        raise RuntimeError("incident_diagnostic_permit_required")
    receipt = launch_disposable_drill_client(config)
    receipt["artifact_sha256"] = artifact_sha256
    receipt["incident_id"] = decision.incident_id
    receipt["admission_reason"] = decision.reason
    receipt = _with_image_contract(
        receipt,
        image_contract=image_contract,
        selected_role=POSTGRES_DRILL_IMAGE_ROLE,
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
