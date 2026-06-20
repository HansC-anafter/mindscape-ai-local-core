"""Result-page asset helpers for cloud messaging replies."""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

ASSET_UPLOAD_BASE_ENV_KEYS = (
    "MINDSCAPE_CLOUD_INTEGRATION_API_BASE",
    "MINDSCAPE_CLOUD_GENERATION_API_BASE",
    "CLOUD_PROVIDER_API_BASE",
    "SITE_HUB_API_BASE",
    "SITE_HUB_API_URL",
    "EXECUTION_CONTROL_API_URL",
    "CLOUD_API_URL",
)

ASSET_UPLOAD_TOKEN_ENV_KEYS = (
    "MINDSCAPE_CLOUD_INTEGRATION_UPLOAD_TOKEN",
    "CLOUD_PROVIDER_UPLOAD_TOKEN",
    "SITE_HUB_UPLOAD_TOKEN",
    "SITE_HUB_API_TOKEN",
)

def clean_text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def append_unique_text(values: List[str], value: Optional[str]) -> None:
    if value and value not in values:
        values.append(value)


def is_public_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def resolve_asset_upload_base() -> Optional[str]:
    for key in ASSET_UPLOAD_BASE_ENV_KEYS:
        value = os.getenv(key)
        if value and value.strip():
            return value.strip().rstrip("/")
    return None


def resolve_asset_upload_token() -> Optional[str]:
    for key in ASSET_UPLOAD_TOKEN_ENV_KEYS:
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    return None


def candidate_file_path(payload: Dict[str, Any]) -> Optional[str]:
    metadata = as_mapping(payload.get("metadata"))
    for key in ("actual_file_path", "file_path", "storage_ref", "path", "uri"):
        value = payload.get(key) or metadata.get(key)
        if is_public_url(value):
            continue
        cleaned = clean_text(value)
        if cleaned and (cleaned.startswith("/") or "/" in cleaned):
            return cleaned
    return None


def candidate_public_url(payload: Dict[str, Any]) -> Optional[str]:
    metadata = as_mapping(payload.get("metadata"))
    for key in ("public_url", "url", "external_url", "asset_url", "download_url"):
        value = payload.get(key) or metadata.get(key)
        if is_public_url(value):
            return str(value).strip()
    storage_ref = payload.get("storage_ref") or metadata.get("storage_ref")
    return str(storage_ref).strip() if is_public_url(storage_ref) else None


def asset_candidate_from_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metadata = as_mapping(payload.get("metadata"))
    file_path = candidate_file_path(payload)
    public_url = candidate_public_url(payload)
    artifact_id = clean_text(
        payload.get("artifact_id")
        or payload.get("id")
        or metadata.get("artifact_id")
    )
    artifact_kind = clean_text(
        payload.get("artifact_kind")
        or payload.get("artifact_type")
        or payload.get("type")
        or metadata.get("artifact_kind")
        or metadata.get("artifact_type")
    )

    has_asset_shape = bool(file_path or public_url) or any(
        key in payload or key in metadata
        for key in (
            "artifact_id",
            "artifact_kind",
            "artifact_type",
            "actual_file_path",
            "file_path",
            "storage_ref",
            "external_url",
        )
    )
    if not has_asset_shape:
        return None

    title = clean_text(
        payload.get("title")
        or payload.get("name")
        or metadata.get("title")
        or metadata.get("name")
    )
    if not title and file_path:
        title = Path(file_path).name
    if not title and public_url:
        title = Path(public_url.split("?", 1)[0]).name or "artifact"
    if not title and artifact_id:
        title = artifact_id

    return {
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "title": title,
        "file_path": file_path,
        "url": public_url,
    }


def collect_asset_candidates(value: Any, *, depth: int = 0) -> List[Dict[str, Any]]:
    if depth > 8:
        return []

    found: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        candidate = asset_candidate_from_payload(value)
        if candidate:
            found.append(candidate)
        for key, nested in value.items():
            if key == "metadata":
                continue
            found.extend(collect_asset_candidates(nested, depth=depth + 1))
    elif isinstance(value, list):
        for item in value:
            found.extend(collect_asset_candidates(item, depth=depth + 1))
    return dedupe_asset_candidates(found)


def collect_execution_ids(value: Any, *, depth: int = 0) -> List[str]:
    if depth > 8:
        return []
    found: List[str] = []
    if isinstance(value, dict):
        append_unique_text(found, clean_text(value.get("execution_id")))
        for nested in value.values():
            for execution_id in collect_execution_ids(nested, depth=depth + 1):
                append_unique_text(found, execution_id)
    elif isinstance(value, list):
        for item in value:
            for execution_id in collect_execution_ids(item, depth=depth + 1):
                append_unique_text(found, execution_id)
    return found


def dedupe_asset_candidates(
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: Dict[Any, Dict[str, Any]] = {}
    for candidate in candidates:
        key = candidate.get("artifact_id") or (
            candidate.get("file_path"),
            candidate.get("url"),
            candidate.get("title"),
        )
        existing = seen.get(key)
        if existing:
            for field in ("file_path", "url", "title", "artifact_kind"):
                if not existing.get(field) and candidate.get(field):
                    existing[field] = candidate[field]
            continue
        seen[key] = candidate
        deduped.append(candidate)
    return deduped


def asset_candidate_from_model(artifact: Any) -> Optional[Dict[str, Any]]:
    if artifact is None:
        return None
    metadata = as_mapping(getattr(artifact, "metadata", None))
    storage_ref = clean_text(getattr(artifact, "storage_ref", None))
    payload = {
        "artifact_id": clean_text(getattr(artifact, "id", None)),
        "artifact_kind": clean_text(
            getattr(getattr(artifact, "artifact_type", None), "value", None)
            or getattr(artifact, "artifact_type", None)
        ),
        "title": clean_text(getattr(artifact, "title", None)),
        "storage_ref": storage_ref,
        "metadata": metadata,
    }
    return asset_candidate_from_payload(payload)


async def upload_page_asset(
    file_path: Path,
    *,
    workspace_id: str,
) -> Optional[str]:
    if not file_path.exists() or not file_path.is_file():
        return None

    base = resolve_asset_upload_base()
    if not base:
        return None

    upload_url = f"{base}/api/v1/assets/upload"
    token = resolve_asset_upload_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            with file_path.open("rb") as file_handle:
                response = await client.post(
                    upload_url,
                    headers=headers,
                    files={"file": (file_path.name, file_handle, mime_type)},
                    data={
                        "workspace_id": workspace_id,
                        "media_type": "meeting_artifact",
                        "filename": file_path.name,
                    },
                )
        response.raise_for_status()
        payload = response.json()
        return clean_text(payload.get("url"))
    except Exception as exc:
        logger.warning(
            "[MessagingHandler] Result page asset upload failed: file=%s error=%s",
            file_path,
            exc,
        )
        return None


async def materialize_page_assets(
    candidates: List[Dict[str, Any]],
    *,
    workspace_id: str,
    upload_func: Callable[..., Awaitable[Optional[str]]] | None = None,
) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    upload = upload_func or upload_page_asset
    for candidate in dedupe_asset_candidates(candidates)[:12]:
        file_path_text = clean_text(candidate.get("file_path"))
        public_url = clean_text(candidate.get("url"))
        file_name = Path(file_path_text).name if file_path_text else None

        if not public_url and file_path_text:
            public_url = await upload(Path(file_path_text), workspace_id=workspace_id)

        title = (
            clean_text(candidate.get("title"))
            or file_name
            or clean_text(candidate.get("artifact_id"))
            or "artifact"
        )
        assets.append(
            {
                "title": title,
                "filename": file_name,
                "url": public_url,
                "artifact_id": clean_text(candidate.get("artifact_id")),
                "artifact_kind": clean_text(candidate.get("artifact_kind")),
            }
        )
    return assets


def escape_markdown_label(value: str) -> str:
    return value.replace("[", "\\[").replace("]", "\\]")


def format_page_assets_md(assets: List[Dict[str, Any]]) -> str:
    if not assets:
        return ""

    lines = ["## 📎 產出檔案", ""]
    for asset in assets:
        label = escape_markdown_label(
            clean_text(asset.get("title"))
            or clean_text(asset.get("filename"))
            or clean_text(asset.get("artifact_id"))
            or "artifact"
        )
        details = [
            item
            for item in (
                clean_text(asset.get("artifact_kind")),
                (
                    f"`{asset.get('artifact_id')}`"
                    if clean_text(asset.get("artifact_id"))
                    else None
                ),
            )
            if item
        ]
        suffix = f" — {' · '.join(details)}" if details else ""
        url = clean_text(asset.get("url"))
        if url:
            lines.append(f"- [{label}]({url}){suffix}")
        else:
            lines.append(f"- {label}{suffix}（已產出，尚未建立公開下載連結）")
    lines.append("")
    return "\n".join(lines)
