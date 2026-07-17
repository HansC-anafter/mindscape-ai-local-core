"""Capability install job execution and terminal coordination."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Mapping, Optional

from backend.app.database.write_readiness import (
    DatabaseWriteNotReadyError,
    wait_for_core_write_readiness,
)
from backend.app.routes.core.capability_install_core.pipeline import run_install_pipeline
from backend.app.routes.core.capability_install_core.install_commit_core.original_path_smoke import (
    verify_original_path_smoke,
)
from backend.app.services import capability_install_job_integrity as install_integrity
from backend.app.services.capability_install_jobs_core.errors import (
    install_job_exception_message,
)
from backend.app.services.runtime_database_incident_gate import (
    RuntimeDatabaseMutationBlocked,
    require_runtime_database_mutation_allowed,
    runtime_database_mutation_context,
)

from .terminal_commit import (
    commit_succeeded_install,
    pipeline_payload,
    restore_previous_candidate,
)

logger = logging.getLogger(__name__)


async def _restore_previous_runtime(
    service: Any,
    result: Any,
    *,
    install_id: str,
) -> dict[str, Any]:
    previous = restore_previous_candidate(result)
    manifest_hash = previous.get("manifest_hash")
    if not manifest_hash:
        return {"state": "restored_no_previous_runtime"}
    activation = await service._notify_execution_activation(
        install_id=install_id,
        pipeline_payload={
            "capability_code": previous["capability_code"],
            "activation_candidate": {"manifest_hash": manifest_hash},
        },
    )
    if activation.get("state") != "activated":
        raise RuntimeError("previous_execution_activation_failed")
    return activation


async def execute_pipeline_job(
    service: Any,
    job: Mapping[str, Any],
    *,
    fastapi_app: Any,
) -> Any:
    payload = dict(job.get("source_payload") or {})
    source_kind = job.get("source_kind")
    await asyncio.to_thread(
        wait_for_core_write_readiness,
        operation=f"capability_install_job:{job['install_id']}",
        timeout_seconds=1,
        poll_interval_seconds=0.2,
    )
    with runtime_database_mutation_context(
        artifact_sha256=payload.get("archive_sha256"),
        source_commit=payload.get("source_commit"),
        install_id=job.get("install_id"),
    ):
        if source_kind == "file_upload":
            install_integrity.verify_file_upload_archive(dict(job))
            return await run_install_pipeline(
                fastapi_app=fastapi_app,
                mindpack_path=Path(payload["mindpack_path"]),
                allow_overwrite=bool(payload.get("allow_overwrite")),
                overwrite_review_confirmation=payload.get(
                    "overwrite_review_confirmation", ""
                ),
                source_label="install-job:file-upload",
                extra_metadata={
                    "installed_from_file": True,
                    "install_id": job["install_id"],
                    "archive_sha256": payload.get("archive_sha256"),
                    "backout_receipt": payload.get("backout_receipt"),
                },
            )
        if source_kind == "cloud_provider_pack":
            pack_file = await service._download_cloud_pack(dict(job))
            try:
                return await run_install_pipeline(
                    fastapi_app=fastapi_app,
                    mindpack_path=pack_file,
                    allow_overwrite=bool(payload.get("allow_overwrite")),
                    overwrite_review_confirmation=payload.get(
                        "overwrite_review_confirmation", ""
                    ),
                    source_label="install-job:cloud-provider-pack",
                    extra_metadata={
                        "installed_from_cloud": True,
                        "install_id": job["install_id"],
                        "provider_id": payload.get("provider_id"),
                        "pack_ref": payload.get("pack_ref"),
                        "bundle": payload.get("bundle"),
                        "archive_sha256": install_integrity.sha256_file(pack_file),
                        "backout_receipt": payload.get("backout_receipt"),
                    },
                )
            finally:
                try:
                    if pack_file.exists():
                        pack_file.unlink()
                except Exception as exc:
                    logger.warning("Failed to clean downloaded pack file: %s", exc)
    raise ValueError(f"Unsupported install job source_kind: {source_kind}")


async def run_next_job(
    service: Any,
    *,
    fastapi_app: Any,
) -> Optional[dict[str, Any]]:
    from backend.app.services.pack_install_reconciliation import (
        poll_install_reconciliation_once,
    )

    try:
        reconciliation = await asyncio.to_thread(poll_install_reconciliation_once)
    except RuntimeDatabaseMutationBlocked as exc:
        return {
            "kind": "pack_install_reconciliation",
            "ok": False,
            "state": "waiting_db_incident",
            "incident_id": exc.decision.incident_id,
            "retry_after_seconds": exc.decision.retry_after_seconds,
        }
    if reconciliation is not None:
        return reconciliation
    job = service.store.claim_next_job()
    if job is None:
        return None
    install_id = str(job["install_id"])
    source_payload = dict(job.get("source_payload") or {})
    result = None
    try:
        require_runtime_database_mutation_allowed(
            f"capability_install_job:{install_id}",
            evidence={
                "artifact_sha256": str(
                    source_payload.get("archive_sha256") or ""
                ),
                "source_commit": str(source_payload.get("source_commit") or ""),
            },
        )
        result = await execute_pipeline_job(service, job, fastapi_app=fastapi_app)
        payload = pipeline_payload(result)
        activation = await service._notify_execution_activation(
            install_id=install_id,
            pipeline_payload=payload,
        )
        payload["execution_activation"] = activation
        payload = install_integrity.attach_install_integrity_evidence(
            job=job,
            result_payload=payload,
        )
        payload = service._refresh_restart_payload(
            payload,
            execution_activation=activation,
            activation=payload.get("activation_candidate"),
        )
        if activation.get("state") == "pending_execution_activation":
            payload["previous_execution_activation"] = await _restore_previous_runtime(
                service,
                result,
                install_id=install_id,
            )
            return service.store.mark_pending_execution_activation(
                install_id,
                result_payload=payload,
                error=activation.get("error"),
            )
        smoke_receipt = await asyncio.to_thread(verify_original_path_smoke)
        payload["original_path_smoke"] = smoke_receipt.to_payload()
        return commit_succeeded_install(
            service=service,
            job=job,
            result=result,
            payload=payload,
            execution_activation=activation,
        )
    except RuntimeDatabaseMutationBlocked as exc:
        return service.store.mark_waiting_db_incident(
            install_id,
            incident_id=exc.decision.incident_id,
            retry_after_seconds=exc.decision.retry_after_seconds,
        )
    except DatabaseWriteNotReadyError as exc:
        readiness = exc.readiness
        return service.store.mark_waiting_db(
            install_id,
            reason=readiness.reason,
            retry_after_seconds=readiness.retry_after_seconds,
        )
    except Exception as exc:
        coordinator = (
            getattr(result, "install_commit_coordinator", None)
            if result is not None
            else None
        )
        if result is not None and not bool(
            getattr(coordinator, "truth_committed", False)
        ):
            try:
                await _restore_previous_runtime(
                    service,
                    result,
                    install_id=install_id,
                )
            except Exception:
                logger.exception(
                    "Capability install previous-tree restoration failed: install_id=%s",
                    install_id,
                )
        logger.error(
            "Capability install job failed: install_id=%s error=%s",
            install_id,
            exc,
            exc_info=True,
        )
        return service.store.mark_failed(
            install_id,
            error=install_job_exception_message(exc),
        )
