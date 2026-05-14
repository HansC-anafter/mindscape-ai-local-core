"""Postgres store for pointer-only artifact and media manifests."""

import hashlib
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase


class ArtifactManifestStore(PostgresStoreBase):
    """Store bounded artifact and media metadata for data-plane objects."""

    def upsert_result_manifest(
        self,
        *,
        artifact_id: str,
        workspace_id: str,
        task_id: Optional[str],
        execution_id: Optional[str],
        result_descriptor: Dict[str, Any],
        storage_ref: Optional[str],
        summary: Optional[str],
    ) -> Dict[str, Any]:
        result_object = dict(result_descriptor.get("result_object") or {})
        object_key = str(result_object.get("object_key") or "").strip()
        if not object_key:
            raise ValueError("result manifest requires result_object.object_key")

        manifest = {
            "artifact_id": artifact_id,
            "workspace_id": workspace_id,
            "task_id": task_id,
            "execution_id": execution_id,
            "object_key": object_key,
            "storage_ref": storage_ref,
            "result_json_path": result_object.get("result_json_path"),
            "checksum_sha256": result_object.get("checksum_sha256"),
            "bytes": int(result_object.get("bytes") or 0),
            "mime_type": result_object.get("mime_type") or "application/json",
            "payload_schema": result_object.get("payload_schema") or "task_result",
            "schema_version": int(result_object.get("schema_version") or 1),
            "summary": summary or result_descriptor.get("summary"),
        }
        self._validate_result_manifest(manifest)

        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO artifact_manifest (
                        artifact_id, workspace_id, task_id, execution_id, object_key,
                        storage_ref, result_json_path, checksum_sha256, bytes, mime_type,
                        payload_schema, schema_version, summary
                    ) VALUES (
                        :artifact_id, :workspace_id, :task_id, :execution_id, :object_key,
                        :storage_ref, :result_json_path, :checksum_sha256, :bytes, :mime_type,
                        :payload_schema, :schema_version, :summary
                    )
                    ON CONFLICT (artifact_id) DO UPDATE SET
                        workspace_id = EXCLUDED.workspace_id,
                        task_id = EXCLUDED.task_id,
                        execution_id = EXCLUDED.execution_id,
                        object_key = EXCLUDED.object_key,
                        storage_ref = EXCLUDED.storage_ref,
                        result_json_path = EXCLUDED.result_json_path,
                        checksum_sha256 = EXCLUDED.checksum_sha256,
                        bytes = EXCLUDED.bytes,
                        mime_type = EXCLUDED.mime_type,
                        payload_schema = EXCLUDED.payload_schema,
                        schema_version = EXCLUDED.schema_version,
                        summary = EXCLUDED.summary,
                        updated_at = now()
                    RETURNING *
                    """
                ),
                manifest,
            ).fetchone()
            search_text = self._build_search_text(manifest)
            conn.execute(
                text(
                    """
                    INSERT INTO artifact_search_index (
                        artifact_id, workspace_id, task_id, execution_id, object_key,
                        summary, search_text, schema_version, created_at
                    ) VALUES (
                        :artifact_id, :workspace_id, :task_id, :execution_id, :object_key,
                        :summary, :search_text, :schema_version, now()
                    )
                    ON CONFLICT (artifact_id) DO UPDATE SET
                        workspace_id = EXCLUDED.workspace_id,
                        task_id = EXCLUDED.task_id,
                        execution_id = EXCLUDED.execution_id,
                        object_key = EXCLUDED.object_key,
                        summary = EXCLUDED.summary,
                        search_text = EXCLUDED.search_text,
                        schema_version = EXCLUDED.schema_version,
                        updated_at = now()
                    """
                ),
                {**manifest, "search_text": search_text},
            )
            return dict(row._mapping if hasattr(row, "_mapping") else row)

    def upsert_media_asset(
        self,
        *,
        workspace_id: str,
        content_hash: str,
        owner_id: Optional[str] = None,
        mime_type: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        asset_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_hash = str(content_hash or "").strip()
        if not normalized_hash:
            raise ValueError("media asset requires content_hash")
        params = {
            "asset_id": asset_id or self._asset_id(workspace_id, normalized_hash),
            "workspace_id": workspace_id,
            "owner_id": owner_id,
            "content_hash": normalized_hash,
            "mime_type": mime_type,
            "width": width,
            "height": height,
        }
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO media_assets (
                        asset_id, workspace_id, owner_id, content_hash,
                        mime_type, width, height
                    ) VALUES (
                        :asset_id, :workspace_id, :owner_id, :content_hash,
                        :mime_type, :width, :height
                    )
                    ON CONFLICT (workspace_id, content_hash) DO UPDATE SET
                        owner_id = COALESCE(EXCLUDED.owner_id, media_assets.owner_id),
                        mime_type = COALESCE(EXCLUDED.mime_type, media_assets.mime_type),
                        width = COALESCE(EXCLUDED.width, media_assets.width),
                        height = COALESCE(EXCLUDED.height, media_assets.height),
                        updated_at = now()
                    RETURNING *
                    """
                ),
                params,
            ).fetchone()
            asset = dict(row._mapping if hasattr(row, "_mapping") else row)
            self._refresh_asset_gallery_projection(conn, asset["asset_id"])
            return asset

    def upsert_media_object(
        self,
        *,
        asset_id: str,
        workspace_id: str,
        object_role: str,
        object_key: str,
        bytes_count: int,
        checksum_sha256: str,
        storage_class: Optional[str] = None,
        mime_type: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        object_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        role = str(object_role or "").strip()
        key = str(object_key or "").strip()
        if role not in {"original", "thumb_512", "preview_webp"}:
            raise ValueError("unsupported media object role")
        if not key:
            raise ValueError("media object requires object_key")
        params = {
            "object_id": object_id or str(uuid.uuid4()),
            "asset_id": asset_id,
            "workspace_id": workspace_id,
            "object_role": role,
            "object_key": key,
            "bytes": int(bytes_count),
            "checksum_sha256": checksum_sha256,
            "storage_class": storage_class,
            "mime_type": mime_type,
            "width": width,
            "height": height,
        }
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO media_objects (
                        object_id, asset_id, workspace_id, object_role, object_key,
                        bytes, checksum_sha256, storage_class, mime_type, width, height
                    ) VALUES (
                        :object_id, :asset_id, :workspace_id, :object_role, :object_key,
                        :bytes, :checksum_sha256, :storage_class, :mime_type, :width, :height
                    )
                    ON CONFLICT (asset_id, object_role) DO UPDATE SET
                        object_key = EXCLUDED.object_key,
                        bytes = EXCLUDED.bytes,
                        checksum_sha256 = EXCLUDED.checksum_sha256,
                        storage_class = EXCLUDED.storage_class,
                        mime_type = COALESCE(EXCLUDED.mime_type, media_objects.mime_type),
                        width = COALESCE(EXCLUDED.width, media_objects.width),
                        height = COALESCE(EXCLUDED.height, media_objects.height),
                        updated_at = now()
                    RETURNING *
                    """
                ),
                params,
            ).fetchone()
            media_object = dict(row._mapping if hasattr(row, "_mapping") else row)
            self._refresh_asset_gallery_projection(conn, asset_id)
            return media_object

    @staticmethod
    def _asset_id(workspace_id: str, content_hash: str) -> str:
        seed = f"{workspace_id}:{content_hash}".encode("utf-8")
        return hashlib.sha256(seed).hexdigest()

    @staticmethod
    def _build_search_text(manifest: Dict[str, Any]) -> str:
        parts = [
            manifest.get("summary"),
            manifest.get("object_key"),
            manifest.get("execution_id"),
            manifest.get("task_id"),
        ]
        return " ".join(str(part).strip() for part in parts if part)

    @staticmethod
    def _validate_result_manifest(manifest: Dict[str, Any]) -> None:
        if not manifest.get("checksum_sha256"):
            raise ValueError("result manifest requires checksum_sha256")
        if int(manifest.get("bytes") or 0) < 0:
            raise ValueError("result manifest bytes must be nonnegative")
        if not manifest.get("workspace_id"):
            raise ValueError("result manifest requires workspace_id")
        if not manifest.get("artifact_id"):
            raise ValueError("result manifest requires artifact_id")

    def _refresh_asset_gallery_projection(self, conn, asset_id: str) -> None:
        conn.execute(
            text(
                """
                INSERT INTO asset_gallery_projection (
                    asset_id, workspace_id, owner_id, content_hash, mime_type,
                    width, height, original_object_key, thumbnail_object_key,
                    preview_object_key, created_at, updated_at
                )
                SELECT
                    a.asset_id,
                    a.workspace_id,
                    a.owner_id,
                    a.content_hash,
                    a.mime_type,
                    a.width,
                    a.height,
                    max(CASE WHEN o.object_role = 'original' THEN o.object_key END),
                    max(CASE WHEN o.object_role = 'thumb_512' THEN o.object_key END),
                    max(CASE WHEN o.object_role = 'preview_webp' THEN o.object_key END),
                    a.created_at,
                    now()
                FROM media_assets a
                LEFT JOIN media_objects o ON o.asset_id = a.asset_id
                WHERE a.asset_id = :asset_id
                GROUP BY
                    a.asset_id, a.workspace_id, a.owner_id, a.content_hash,
                    a.mime_type, a.width, a.height, a.created_at
                ON CONFLICT (asset_id) DO UPDATE SET
                    workspace_id = EXCLUDED.workspace_id,
                    owner_id = EXCLUDED.owner_id,
                    content_hash = EXCLUDED.content_hash,
                    mime_type = EXCLUDED.mime_type,
                    width = EXCLUDED.width,
                    height = EXCLUDED.height,
                    original_object_key = EXCLUDED.original_object_key,
                    thumbnail_object_key = EXCLUDED.thumbnail_object_key,
                    preview_object_key = EXCLUDED.preview_object_key,
                    updated_at = now()
                """
            ),
            {"asset_id": asset_id},
        )
