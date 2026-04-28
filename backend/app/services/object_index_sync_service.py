"""Shared runtime sync service for concrete Addressable Object instances."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from backend.app.models.object_runtime import (
    ObjectInstanceRecord,
    ObjectInstanceSyncRequest,
    ObjectInstanceSyncResponse,
    ObjectInstanceSyncSourceResult,
    ObjectRef,
)
from backend.app.services.object_catalog_registry import ObjectCatalogRegistry
from backend.app.services.stores.object_instance_registry_store import (
    ObjectInstanceRegistryStore,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _resolve_local_core_root() -> Path:
    return Path(__file__).resolve().parents[3]


async def _invoke_backend_callable(backend_path: str, **kwargs: Any) -> Any:
    module_path, attr_name = backend_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    target = getattr(module, attr_name)
    signature = inspect.signature(target)
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        invocation_kwargs = kwargs
    else:
        invocation_kwargs = {
            key: value for key, value in kwargs.items() if key in signature.parameters
        }
    result = target(**invocation_kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _validate_object_ref_identity(ref: ObjectRef, workspace_id: str) -> None:
    expected_uri = f"mindscape://{ref.owner_pack}/{ref.object_kind}/{ref.object_id}"
    if ref.uri != expected_uri:
        raise ValueError(
            "invalid_object_ref_uri:"
            f"expected={expected_uri}:provided={ref.uri}"
        )
    if ref.workspace_id and ref.workspace_id != workspace_id:
        raise ValueError(
            "invalid_object_ref_workspace:"
            f"expected={workspace_id}:provided={ref.workspace_id}"
        )


def _coerce_indexer_records(
    payload: Any,
    *,
    workspace_id: str,
    owner_pack: str,
    object_kind: str,
) -> List[ObjectInstanceRecord]:
    if payload is None:
        return []
    if not isinstance(payload, dict):
        raise ValueError("indexer_backend_returned_non_object")

    raw_records = payload.get("records")
    if raw_records is None:
        return []
    if not isinstance(raw_records, list):
        raise ValueError("indexer_backend_records_must_be_array")

    records: List[ObjectInstanceRecord] = []
    for index, raw_record in enumerate(raw_records):
        try:
            record = (
                raw_record
                if isinstance(raw_record, ObjectInstanceRecord)
                else ObjectInstanceRecord.model_validate(raw_record)
            )
        except Exception as exc:
            raise ValueError(f"invalid_indexer_record:{index}:{exc}") from exc

        if record.ref.owner_pack != owner_pack or record.ref.object_kind != object_kind:
            raise ValueError(
                "indexer_record_kind_mismatch:"
                f"{record.ref.owner_pack}.{record.ref.object_kind}"
            )
        _validate_object_ref_identity(record.ref, workspace_id)
        records.append(record)

    return records


class ObjectIndexSyncStatusTracker:
    """In-memory health snapshot for AOL object index sync lifecycle."""

    def __init__(self) -> None:
        self.state = "idle"
        self.last_reason: str | None = None
        self.last_started_at: str | None = None
        self.last_completed_at: str | None = None
        self.last_error: str | None = None
        self.runs_started = 0
        self.runs_completed = 0
        self.workspaces: Dict[str, Dict[str, Any]] = {}

    def mark_run_started(self, *, reason: str, workspace_ids: List[str]) -> None:
        self.state = "running"
        self.last_reason = reason
        self.last_started_at = _utc_now_iso()
        self.last_error = None
        self.runs_started += 1
        for workspace_id in workspace_ids:
            self.workspaces.setdefault(workspace_id, {})

    def mark_run_completed(self) -> None:
        self.state = "completed"
        self.last_completed_at = _utc_now_iso()
        self.runs_completed += 1

    def mark_run_failed(self, error: str) -> None:
        self.state = "failed"
        self.last_completed_at = _utc_now_iso()
        self.last_error = error

    def mark_disabled(self, reason: str) -> None:
        self.state = "disabled"
        self.last_reason = reason
        self.last_error = None

    def mark_workspace_started(self, workspace_id: str, *, reason: str | None) -> None:
        self.workspaces[workspace_id] = {
            **self.workspaces.get(workspace_id, {}),
            "status": "running",
            "reason": reason,
            "last_started_at": _utc_now_iso(),
            "last_error": None,
        }

    def mark_workspace_completed(
        self,
        workspace_id: str,
        *,
        indexed_count: int,
        source_count: int,
    ) -> None:
        self.workspaces[workspace_id] = {
            **self.workspaces.get(workspace_id, {}),
            "status": "completed",
            "indexed_count": indexed_count,
            "source_count": source_count,
            "last_completed_at": _utc_now_iso(),
            "last_error": None,
        }

    def mark_workspace_failed(self, workspace_id: str, *, error: str) -> None:
        self.workspaces[workspace_id] = {
            **self.workspaces.get(workspace_id, {}),
            "status": "failed",
            "last_completed_at": _utc_now_iso(),
            "last_error": error,
        }

    def snapshot(self, *, workspace_id: str | None = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "state": self.state,
            "last_reason": self.last_reason,
            "last_started_at": self.last_started_at,
            "last_completed_at": self.last_completed_at,
            "last_error": self.last_error,
            "runs_started": self.runs_started,
            "runs_completed": self.runs_completed,
        }
        if workspace_id:
            payload["workspace_id"] = workspace_id
            payload["workspace"] = self.workspaces.get(workspace_id)
        else:
            payload["workspace_count"] = len(self.workspaces)
            payload["workspaces"] = dict(self.workspaces)
        return payload


object_index_sync_status = ObjectIndexSyncStatusTracker()


class ObjectIndexSyncService:
    """Discover catalog indexers and write their concrete instances."""

    def __init__(
        self,
        *,
        catalog: ObjectCatalogRegistry | None = None,
        instance_store: ObjectInstanceRegistryStore | None = None,
        workspace_store: PostgresStoreBase | None = None,
        status_tracker: ObjectIndexSyncStatusTracker | None = None,
    ) -> None:
        self.catalog = catalog or ObjectCatalogRegistry(_resolve_local_core_root())
        self.instance_store = instance_store or ObjectInstanceRegistryStore()
        self.workspace_store = workspace_store or PostgresStoreBase(db_role="core")
        self.status = status_tracker or object_index_sync_status

    def list_recent_workspace_ids(self, *, limit: int = 50) -> List[str]:
        bounded_limit = max(1, min(limit, 250))
        query = text(
            """
            SELECT id
            FROM workspaces
            ORDER BY COALESCE(updated_at, created_at) DESC NULLS LAST, id ASC
            LIMIT :limit
            """
        )
        with self.workspace_store.get_connection() as conn:
            rows = conn.execute(query, {"limit": bounded_limit}).fetchall()
        return [str(row._mapping["id"]) for row in rows if row._mapping.get("id")]

    async def sync_workspace(
        self,
        workspace_id: str,
        request: ObjectInstanceSyncRequest,
    ) -> ObjectInstanceSyncResponse:
        self.status.mark_workspace_started(workspace_id, reason=request.reason)
        try:
            response = await self._sync_workspace(workspace_id, request)
            self.status.mark_workspace_completed(
                workspace_id,
                indexed_count=response.indexed_count,
                source_count=len(response.sources),
            )
            return response
        except Exception as exc:
            self.status.mark_workspace_failed(workspace_id, error=str(exc))
            raise

    async def _sync_workspace(
        self,
        workspace_id: str,
        request: ObjectInstanceSyncRequest,
    ) -> ObjectInstanceSyncResponse:
        entries = self.catalog.list_entries(
            owner_pack=request.owner_pack,
            object_kind=request.object_kind,
        )

        total_indexed_count = 0
        source_results: List[ObjectInstanceSyncSourceResult] = []
        for entry_payload in entries:
            owner_pack = _text(entry_payload.get("owner_pack"))
            object_kind = _text(entry_payload.get("object_kind"))
            indexer_backend = _text(entry_payload.get("indexer_backend"))
            if not indexer_backend:
                source_results.append(
                    ObjectInstanceSyncSourceResult(
                        owner_pack=owner_pack,
                        object_kind=object_kind,
                        indexer_backend="",
                        indexed_count=0,
                        status="skipped",
                        message="No indexer_backend declared.",
                    )
                )
                continue

            try:
                payload = await _invoke_backend_callable(
                    indexer_backend,
                    workspace_id=workspace_id,
                    owner_pack=owner_pack,
                    object_kind=object_kind,
                    limit=request.limit,
                    force=request.force,
                    reason=request.reason,
                    catalog_entry=jsonable_encoder(entry_payload),
                )
                records = _coerce_indexer_records(
                    payload,
                    workspace_id=workspace_id,
                    owner_pack=owner_pack,
                    object_kind=object_kind,
                )
                indexed_count = self.instance_store.upsert_many(workspace_id, records)
                total_indexed_count += indexed_count
                source_results.append(
                    ObjectInstanceSyncSourceResult(
                        owner_pack=owner_pack,
                        object_kind=object_kind,
                        indexer_backend=indexer_backend,
                        indexed_count=indexed_count,
                        status="synced",
                    )
                )
            except Exception as exc:  # pragma: no cover - exact failures are pack-owned
                logger.exception(
                    "Failed to sync object index for %s.%s via %s: %s",
                    owner_pack,
                    object_kind,
                    indexer_backend,
                    exc,
                )
                source_results.append(
                    ObjectInstanceSyncSourceResult(
                        owner_pack=owner_pack,
                        object_kind=object_kind,
                        indexer_backend=indexer_backend,
                        indexed_count=0,
                        status="failed",
                        message=str(exc),
                    )
                )

        return ObjectInstanceSyncResponse(
            workspace_id=workspace_id,
            indexed_count=total_indexed_count,
            sources=source_results,
        )

    async def sync_recent_workspaces(
        self,
        *,
        workspace_limit: int,
        per_workspace_limit: int,
        reason: str,
    ) -> Dict[str, Any]:
        workspace_ids = await asyncio.to_thread(
            self.list_recent_workspace_ids,
            limit=workspace_limit,
        )
        self.status.mark_run_started(reason=reason, workspace_ids=workspace_ids)
        summary: Dict[str, Any] = {
            "reason": reason,
            "workspace_count": len(workspace_ids),
            "indexed_count": 0,
            "workspaces": [],
        }
        try:
            for workspace_id in workspace_ids:
                response = await self.sync_workspace(
                    workspace_id,
                    ObjectInstanceSyncRequest(
                        limit=per_workspace_limit,
                        reason=reason,
                    ),
                )
                summary["indexed_count"] += response.indexed_count
                summary["workspaces"].append(response.model_dump(exclude_none=True))
                await asyncio.sleep(0)
            self.status.mark_run_completed()
            return summary
        except Exception as exc:
            self.status.mark_run_failed(str(exc))
            raise


_object_index_sync_service: ObjectIndexSyncService | None = None


def get_object_index_sync_service() -> ObjectIndexSyncService:
    global _object_index_sync_service
    if _object_index_sync_service is None:
        _object_index_sync_service = ObjectIndexSyncService()
    return _object_index_sync_service


def get_object_index_sync_status() -> ObjectIndexSyncStatusTracker:
    return object_index_sync_status
