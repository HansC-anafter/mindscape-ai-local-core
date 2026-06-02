"""Durable capability install job orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from backend.app.database.write_readiness import (
    DatabaseWriteNotReadyError,
    ensure_core_write_ready,
    wait_for_core_write_readiness,
)
from backend.app.routes.core.capability_install_core.paths import (
    _ensure_sys_path,
    _resolve_local_core_root,
)
from backend.app.routes.core.capability_install_core.pipeline import run_install_pipeline
from backend.app.services.pack_activation_service import PackActivationService
from backend.app.services.stores.capability_install_job_store import (
    CapabilityInstallJobStore,
)

logger = logging.getLogger(__name__)


def _jobs_root() -> Path:
    configured = os.getenv("MINDSCAPE_CAPABILITY_INSTALL_JOBS_DIR")
    if configured:
        return Path(configured)
    return _resolve_local_core_root() / "data" / "capability-install-jobs"


def _status_url(install_id: str) -> str:
    return f"/api/v1/capability-packs/install-jobs/{install_id}"


def _pipeline_result_to_payload(result: Any) -> Dict[str, Any]:
    return {
        "success": bool(getattr(result, "success", False)),
        "capability_code": getattr(result, "capability_code", None),
        "version": getattr(result, "version", None),
        "warnings": list(getattr(result, "warnings", []) or []),
        "restart_required": bool(getattr(result, "restart_required", False)),
        "restart_triggered": bool(getattr(result, "restart_triggered", False)),
        "hot_reload": getattr(result, "hot_reload_result", None),
        "webhook": getattr(result, "webhook_result", None),
        "activation": getattr(result, "activation", None),
        "validation": getattr(result, "validation", None),
        "pack_metadata": getattr(result, "pack_metadata", {}) or {},
    }


class CapabilityInstallJobService:
    """Create and execute capability install jobs."""

    def __init__(
        self,
        store: Optional[CapabilityInstallJobStore] = None,
        activation_service: Optional[PackActivationService] = None,
    ):
        self.store = store or CapabilityInstallJobStore()
        self._activation_service = activation_service

    def create_file_upload_job(
        self,
        *,
        filename: str,
        content: bytes,
        allow_overwrite: bool,
        overwrite_review_confirmation: str,
        profile_id: str,
    ) -> Dict[str, Any]:
        ensure_core_write_ready(operation="capability_install_job_create:file_upload")
        install_id = uuid.uuid4().hex
        job_dir = _jobs_root() / install_id
        job_dir.mkdir(parents=True, exist_ok=True)
        mindpack_path = job_dir / "input.mindpack"
        mindpack_path.write_bytes(content)
        job = self.store.create_job(
            install_id=install_id,
            source_kind="file_upload",
            source_payload={
                "filename": filename,
                "mindpack_path": str(mindpack_path),
                "allow_overwrite": allow_overwrite,
                "overwrite_review_confirmation": overwrite_review_confirmation,
                "profile_id": profile_id,
            },
        )
        job["status_url"] = _status_url(install_id)
        return job

    def create_cloud_pack_job(
        self,
        *,
        provider_id: str,
        pack_ref: str,
        verify_checksum: bool,
        allow_overwrite: bool,
        overwrite_review_confirmation: str,
        profile_id: str,
        bundle: Optional[str] = None,
        pack_code: Optional[str] = None,
        download_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        ensure_core_write_ready(operation="capability_install_job_create:cloud_pack")
        install_id = uuid.uuid4().hex
        (_jobs_root() / install_id).mkdir(parents=True, exist_ok=True)
        job = self.store.create_job(
            install_id=install_id,
            source_kind="cloud_provider_pack",
            source_payload={
                "provider_id": provider_id,
                "pack_ref": pack_ref,
                "verify_checksum": verify_checksum,
                "allow_overwrite": allow_overwrite,
                "overwrite_review_confirmation": overwrite_review_confirmation,
                "profile_id": profile_id,
                "bundle": bundle,
                "pack_code": pack_code,
                "download_url": download_url,
            },
        )
        job["status_url"] = _status_url(install_id)
        return job

    def get_job(self, install_id: str) -> Optional[Dict[str, Any]]:
        job = self.store.get_job(install_id)
        if job is not None:
            job = self._reconcile_pending_execution_activation(job)
            job["status_url"] = _status_url(install_id)
        return job

    def _get_activation_service(self) -> PackActivationService:
        if self._activation_service is None:
            self._activation_service = PackActivationService()
        return self._activation_service

    def _reconcile_pending_execution_activation(
        self,
        job: Dict[str, Any],
    ) -> Dict[str, Any]:
        if job.get("state") != "pending_execution_activation":
            return job
        result_payload = job.get("result_payload") or {}
        capability_code = result_payload.get("capability_code")
        if not capability_code:
            return job
        try:
            activation = self._get_activation_service().get_state(capability_code)
        except Exception as exc:
            logger.warning(
                "Failed to reconcile capability install activation for %s: %s",
                capability_code,
                exc,
                exc_info=True,
            )
            return job
        if not self._activation_matches_pending_job(
            capability_code=capability_code,
            result_payload=result_payload,
            activation=activation,
        ):
            return job
        next_payload = dict(result_payload)
        next_payload["activation"] = activation
        next_payload["execution_activation"] = {
            "state": "activated",
            "source": "activation_state_reconcile",
            "activation_state": activation.get("activation_state"),
            "activation_mode": activation.get("activation_mode"),
            "updated_at": activation.get("updated_at"),
        }
        reconciled = self.store.mark_succeeded(
            job["install_id"],
            result_payload=next_payload,
        )
        return reconciled or job

    @staticmethod
    def _activation_matches_pending_job(
        *,
        capability_code: str,
        result_payload: Dict[str, Any],
        activation: Optional[Dict[str, Any]],
    ) -> bool:
        if not activation:
            return False
        if activation.get("pack_id") != capability_code:
            return False
        if activation.get("install_state") != "installed":
            return False
        if activation.get("activation_state") != "active":
            return False
        pending_hash = (result_payload.get("activation") or {}).get("manifest_hash")
        current_hash = activation.get("manifest_hash")
        return bool(pending_hash and current_hash and pending_hash == current_hash)

    async def run_next_job(self, *, fastapi_app: Any) -> Optional[Dict[str, Any]]:
        job = self.store.claim_next_job()
        if job is None:
            return None
        install_id = job["install_id"]
        try:
            result = await self._execute_job(job, fastapi_app=fastapi_app)
            payload = _pipeline_result_to_payload(result)
            activation = await self._notify_execution_activation(
                install_id=install_id,
                pipeline_payload=payload,
            )
            payload["execution_activation"] = activation
            if activation.get("state") == "pending_execution_activation":
                return self.store.mark_pending_execution_activation(
                    install_id,
                    result_payload=payload,
                    error=activation.get("error"),
                )
            return self.store.mark_succeeded(install_id, result_payload=payload)
        except DatabaseWriteNotReadyError as exc:
            readiness = exc.readiness
            return self.store.mark_waiting_db(
                install_id,
                reason=readiness.reason,
                retry_after_seconds=readiness.retry_after_seconds,
            )
        except Exception as exc:
            logger.error(
                "Capability install job failed: install_id=%s error=%s",
                install_id,
                exc,
                exc_info=True,
            )
            return self.store.mark_failed(install_id, error=str(exc))

    async def _execute_job(self, job: Dict[str, Any], *, fastapi_app: Any):
        payload = job.get("source_payload") or {}
        source_kind = job.get("source_kind")
        readiness_kwargs = {
            "operation": f"capability_install_job:{job['install_id']}",
            "timeout_seconds": 1,
            "poll_interval_seconds": 0.2,
        }
        await asyncio.to_thread(wait_for_core_write_readiness, **readiness_kwargs)
        if source_kind == "file_upload":
            return await run_install_pipeline(
                fastapi_app=fastapi_app,
                mindpack_path=Path(payload["mindpack_path"]),
                allow_overwrite=bool(payload.get("allow_overwrite")),
                overwrite_review_confirmation=payload.get(
                    "overwrite_review_confirmation", ""
                ),
                source_label="install-job:file-upload",
                extra_metadata={"installed_from_file": True, "install_id": job["install_id"]},
            )
        if source_kind == "cloud_provider_pack":
            pack_file = await self._download_cloud_pack(job)
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
                    },
                )
            finally:
                try:
                    if pack_file.exists():
                        pack_file.unlink()
                except Exception as exc:
                    logger.warning("Failed to clean downloaded pack file: %s", exc)
        raise ValueError(f"Unsupported install job source_kind: {source_kind}")

    async def _download_cloud_pack(self, job: Dict[str, Any]) -> Path:
        _ensure_sys_path()
        payload = job.get("source_payload") or {}
        provider_id = payload.get("provider_id")
        if not provider_id:
            raise ValueError("Cloud install job missing provider_id")

        from app.routes.core.cloud_providers import get_cloud_manager

        cloud_manager = get_cloud_manager()
        provider = cloud_manager.get_provider(provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' not found")
        if not provider.is_configured():
            raise ValueError(f"Provider '{provider_id}' is not configured")

        job_dir = _jobs_root() / job["install_id"]
        job_dir.mkdir(parents=True, exist_ok=True)
        pack_file = job_dir / "downloaded.mindpack"
        download_url = payload.get("download_url")
        if download_url:
            import httpx

            headers = {}
            api_key = provider.get_api_key() if hasattr(provider, "get_api_key") else None
            if api_key:
                headers["X-API-Key"] = api_key
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(download_url, headers=headers)
                response.raise_for_status()
                pack_file.write_bytes(response.content)
            return pack_file

        from app.services.pack_download_service import get_pack_download_service

        pack_ref = payload.get("pack_ref")
        if not pack_ref:
            raise ValueError("Cloud install job missing pack_ref")
        download_service = get_pack_download_service()
        success, downloaded_file, error_msg = await download_service.download_pack(
            provider=provider,
            pack_ref=pack_ref,
            verify_checksum=bool(payload.get("verify_checksum", True)),
        )
        if not success or not downloaded_file:
            raise ValueError(f"Failed to download pack: {error_msg}")
        shutil.move(str(downloaded_file), str(pack_file))
        return pack_file

    async def _notify_execution_activation(
        self,
        *,
        install_id: str,
        pipeline_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        capability_code = pipeline_payload.get("capability_code")
        if not capability_code:
            return {"state": "skipped", "reason": "missing_capability_code"}
        if os.getenv("MINDSCAPE_EXECUTION_ACTIVATION_DISABLED", "").lower() in {
            "1",
            "true",
            "yes",
        }:
            return {"state": "skipped", "reason": "disabled_by_env"}

        import httpx

        activation_url = os.getenv(
            "MINDSCAPE_EXECUTION_ACTIVATION_URL",
            "http://backend:8200/api/v1/admin/capability-runtime/activate",
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    activation_url,
                    json={
                        "capability_code": capability_code,
                        "install_id": install_id,
                        "reason": "install_job_completed",
                    },
                )
            data = response.json()
            if response.status_code == 202:
                return {
                    "state": "pending_execution_activation",
                    "status_code": response.status_code,
                    "error": data.get("error") or data,
                }
            response.raise_for_status()
            return data
        except Exception as exc:
            return {
                "state": "pending_execution_activation",
                "error": str(exc),
            }


async def run_capability_install_job_worker_loop(
    app: Any,
    *,
    poll_interval_seconds: float = 2.0,
) -> None:
    """Run the single-worker capability install loop."""

    service: Optional[CapabilityInstallJobService] = None
    while True:
        try:
            if service is None:
                service = CapabilityInstallJobService()
            result = await service.run_next_job(fastapi_app=app)
            if result is None:
                await asyncio.sleep(poll_interval_seconds)
            else:
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Capability install job worker iteration failed: %s",
                exc,
                exc_info=True,
            )
            service = None
            await asyncio.sleep(poll_interval_seconds)
