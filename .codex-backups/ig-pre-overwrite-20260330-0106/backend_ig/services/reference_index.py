"""
Reference Index — _index.json manager with file-lock concurrency control.

Provides efficient querying of references without scanning the filesystem.
Delta updates on each pin/delete, full rebuild as fallback.

Concurrency: fcntl advisory lock on _index.json.lock.
"""

import copy
import fcntl
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from capabilities.ig.services.projection_builder import build_projection

logger = logging.getLogger(__name__)

_INDEX_CACHE_LOCK = threading.Lock()
_INDEX_CACHE: Dict[str, tuple[int, int, Dict[str, Any]]] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_timestamp_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def _sortable_text(value: Any) -> str:
    return str(value or "")


def _sortable_timestamp(value: Any) -> str:
    return _normalize_timestamp_text(value)


def _build_counted_options(counts: Dict[str, int]) -> List[Dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )
    ]


def _extract_validated_at(metadata: Dict[str, Any]) -> str:
    return _normalize_timestamp_text(
        (metadata.get("analysis_provenance") or {}).get("validated_at", "")
        or (metadata.get("analysis_job") or {}).get("completed_at", "")
        or ""
    )


def _extract_job_timestamp(
    metadata: Dict[str, Any],
    field: str,
) -> str:
    return _normalize_timestamp_text((metadata.get("analysis_job") or {}).get(field, "") or "")


def _latest_timestamp(*values: Any) -> str:
    normalized = []
    for value in values:
        normalized_value = _normalize_timestamp_text(value)
        if normalized_value:
            normalized.append(normalized_value)
    return max(normalized) if normalized else ""


def _extract_pending_sort_at(metadata: Dict[str, Any]) -> str:
    return _latest_timestamp(
        _extract_job_timestamp(metadata, "queued_at"),
        _extract_job_timestamp(metadata, "started_at"),
        metadata.get("pinned_at", ""),
    )


def _is_reanalyzing_completed_entry(entry: Dict[str, Any]) -> bool:
    status = str(entry.get("analysis_status", "")).strip().upper()
    job_status = str(entry.get("analysis_job_status", "")).strip().upper()
    if status not in {"PENDING", "RUNNING"} or job_status not in {"PENDING", "RUNNING"}:
        return False
    if not entry.get("has_analysis"):
        return False
    return bool(_normalize_timestamp_text(entry.get("validated_at")))


def _resolved_browsing_status(entry: Dict[str, Any]) -> str:
    if _is_reanalyzing_completed_entry(entry):
        return "COMPLETED"
    return str(entry.get("analysis_status", "")).strip().upper()


def _resolve_browsing_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    if not _is_reanalyzing_completed_entry(entry):
        return entry
    resolved = dict(entry)
    resolved.setdefault(
        "analysis_job_status",
        str(entry.get("analysis_status", "")).strip().upper(),
    )
    resolved["analysis_status"] = "COMPLETED"
    return resolved


def _is_pending_queue_candidate(entry: Dict[str, Any]) -> bool:
    return _resolved_browsing_status(entry) != "COMPLETED"


def _build_projection_filters(
    location: Optional[str] = None,
    location_sub: Optional[str] = None,
    shot_type: Optional[str] = None,
    focal_class: Optional[str] = None,
    focal_mm: Optional[str] = None,
    aperture: Optional[str] = None,
    dof: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    light_temp: Optional[str] = None,
    light_intensity: Optional[str] = None,
    time_of_day: Optional[str] = None,
    stance: Optional[str] = None,
    gaze: Optional[str] = None,
    body_orientation: Optional[str] = None,
    expression: Optional[str] = None,
    archetype_tag: Optional[str] = None,
    aesthetic_tag: Optional[str] = None,
    material: Optional[str] = None,
    training_readiness: Optional[str] = None,
    training_lane_hint: Optional[str] = None,
    training_style_tag: Optional[str] = None,
    training_quality_flag: Optional[str] = None,
    identity_cluster_hint: Optional[str] = None,
    look_state_hint: Optional[str] = None,
) -> List[tuple[str, str, str]]:
    projection_filters: List[tuple[str, str, str]] = []
    exact_matches = [
        ("p_location", location),
        ("p_location_sub", location_sub),
        ("p_shot_type", shot_type),
        ("p_focal_class", focal_class),
        ("p_aperture", aperture),
        ("p_dof", dof),
        ("p_aspect_ratio", aspect_ratio),
        ("p_light_temp", light_temp),
        ("p_light_intensity", light_intensity),
        ("p_time_of_day", time_of_day),
        ("p_stance", stance),
        ("p_gaze", gaze),
        ("p_body_orientation", body_orientation),
        ("p_expression", expression),
        ("p_training_readiness", training_readiness),
        ("p_training_identity_cluster_hint", identity_cluster_hint),
        ("p_training_look_state_hint", look_state_hint),
    ]
    for field, value in exact_matches:
        if value is not None:
            projection_filters.append((field, value.strip().lower(), "exact"))

    list_contains = [
        ("p_archetype_tags", archetype_tag),
        ("p_aesthetic_tags", aesthetic_tag),
        ("p_materials", material),
        ("p_training_lane_hints", training_lane_hint),
        ("p_training_style_tags", training_style_tag),
        ("p_training_quality_flags", training_quality_flag),
    ]
    for field, value in list_contains:
        if value is not None:
            projection_filters.append((field, value.strip().lower(), "in_list"))

    if focal_mm:
        projection_filters.append(("p_focal_range", focal_mm.strip().lower(), "substring"))

    return projection_filters


def _flatten_searchable_value(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        flattened: List[str] = []
        for item in value:
            flattened.extend(_flatten_searchable_value(item))
        return flattened
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return [text] if text else []
    return []


def _iter_searchable_entry_fields(entry: Dict[str, Any]):
    base_fields = [
        entry.get("reference_id", ""),
        entry.get("source_handle", ""),
        entry.get("source_shortcode", ""),
        entry.get("analysis_error", ""),
        entry.get("analysis_excerpt", ""),
        *(entry.get("tags") or []),
        *(entry.get("auto_tags") or []),
    ]
    for field in base_fields:
        yield from _flatten_searchable_value(field)

    for key, value in entry.items():
        if key.startswith("p_"):
            yield from _flatten_searchable_value(value)


class ReferenceIndex:
    """Manages _index.json for a workspace's references directory.

    Usage:
        index = ReferenceIndex(references_path)
        index.add_entry(reference_id, metadata_dict)
        results = index.query(source_handle="@xyz", tags=["flat-lay"])
        index.remove_entry(reference_id)
    """

    def __init__(self, references_path: Path):
        self.references_path = references_path
        self.index_path = references_path / "_index.json"
        self.lock_path = references_path / "_index.json.lock"

    def _empty_index(self) -> Dict[str, Any]:
        return {"version": "1.0", "updated_at": _utc_now_iso(), "entries": {}}

    def _cache_key(self) -> str:
        return str(self.index_path.resolve())

    def _update_read_cache(
        self,
        data: Dict[str, Any],
        *,
        mtime_ns: Optional[int] = None,
        size: Optional[int] = None,
    ) -> None:
        try:
            stat = self.index_path.stat()
            cached_mtime_ns = stat.st_mtime_ns
            cached_size = stat.st_size
        except OSError:
            if mtime_ns is None or size is None:
                return
            cached_mtime_ns = mtime_ns
            cached_size = size

        with _INDEX_CACHE_LOCK:
            _INDEX_CACHE[self._cache_key()] = (cached_mtime_ns, cached_size, data)

    def _acquire_lock(self):
        """Acquire advisory file lock."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_fd = open(self.lock_path, "w")
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
        except Exception as e:
            logger.warning("[RefIndex] Lock acquisition failed: %s", e)
            self._lock_fd.close()
            raise

    def _release_lock(self):
        """Release advisory file lock."""
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            self._lock_fd.close()
        except Exception:
            pass

    def _read_index(self, *, mutable: bool = False) -> Dict[str, Any]:
        """Read index from disk."""
        if not self.index_path.exists():
            return self._empty_index()

        cache_key = self._cache_key()
        try:
            stat = self.index_path.stat()
        except OSError:
            return self._empty_index()

        with _INDEX_CACHE_LOCK:
            cached = _INDEX_CACHE.get(cache_key)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return copy.deepcopy(cached[2]) if mutable else cached[2]

        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "entries" not in data:
                logger.warning("[RefIndex] Corrupt index, rebuilding")
                data = self.rebuild()
            self._update_read_cache(
                data,
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
            )
            return copy.deepcopy(data) if mutable else data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("[RefIndex] Failed to read index: %s, rebuilding", e)
            data = self.rebuild()
            self._update_read_cache(
                data,
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
            )
            return copy.deepcopy(data) if mutable else data

    def _write_index(self, data: Dict[str, Any]) -> None:
        """Write index to disk atomically to prevent torn reads."""
        data["updated_at"] = _utc_now_iso()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.index_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.index_path)
        self._update_read_cache(data)

    def add_entry(self, reference_id: str, metadata: Dict[str, Any]) -> None:
        """Add or update a reference entry in the index (delta update)."""
        self._acquire_lock()
        try:
            data = self._read_index(mutable=True)
            entry = {
                "reference_id": reference_id,
                "content_hash": metadata.get("content_hash", ""),
                "source_handle": metadata.get("source_handle", ""),
                "source_shortcode": metadata.get("source_shortcode", ""),
                "tags": metadata.get("tags", []),
                "auto_tags": metadata.get("auto_tags", []),
                "collections": metadata.get("collections", []),
                "pinned_at": _normalize_timestamp_text(metadata.get("pinned_at", _utc_now_iso())),
                "deleted": metadata.get("deleted", False),
                "has_analysis": metadata.get("vision_description") is not None,
                "analysis_status": (
                    (metadata.get("analysis_job") or {}).get("status", "")
                ),
                "project_id": metadata.get("project_id", ""),
                "analysis_profile": (
                    (metadata.get("analysis_provenance") or {}).get("analysis_profile", "")
                ),
                "schema_version": (
                    (metadata.get("analysis_provenance") or {}).get("schema_version", "")
                ),
                "queued_at": _extract_job_timestamp(metadata, "queued_at"),
                "started_at": _extract_job_timestamp(metadata, "started_at"),
                "validated_at": _extract_validated_at(metadata),
                "pending_sort_at": _extract_pending_sort_at(metadata),
                "analysis_error": (
                    (metadata.get("analysis_job") or {}).get("last_error", "")
                ),
                "analysis_failure_stage": (
                    (metadata.get("analysis_debug") or {}).get("failure_stage", "")
                ),
                "analysis_excerpt": (
                    (metadata.get("analysis_debug") or {}).get("description_excerpt", "")
                ),
                "has_thinking": bool(
                    (metadata.get("analysis_debug") or {}).get("thinking_text")
                    or ((metadata.get("vision_description") or {}).get("_thinking"))
                ),
            }
            # Merge V2.0 projection fields if vision_description is present
            vision = metadata.get("vision_description")
            if vision and isinstance(vision, dict):
                entry.update(build_projection(vision))
            data["entries"][reference_id] = entry
            self._write_index(data)
        finally:
            self._release_lock()

    def remove_entry(self, reference_id: str, soft: bool = True) -> None:
        """Mark entry as deleted (soft) or remove from index (hard)."""
        self._acquire_lock()
        try:
            data = self._read_index(mutable=True)
            if reference_id in data["entries"]:
                if soft:
                    data["entries"][reference_id]["deleted"] = True
                else:
                    del data["entries"][reference_id]
                self._write_index(data)
        finally:
            self._release_lock()

    def update_entry_field(self, reference_id: str, field: str, value: Any) -> None:
        """Update a single field on an existing index entry."""
        self._acquire_lock()
        try:
            data = self._read_index(mutable=True)
            if reference_id in data["entries"]:
                data["entries"][reference_id][field] = value
                self._write_index(data)
        finally:
            self._release_lock()

    def _iter_filtered_entries(
        self,
        data: Dict[str, Any],
        source_handle: Optional[str] = None,
        tags: Optional[List[str]] = None,
        collection: Optional[str] = None,
        project_id: Optional[str] = None,
        include_deleted: bool = False,
        analysis_profile: Optional[str] = None,
        analysis_status: Optional[str] = None,
        schema_version: Optional[str] = None,
        has_analysis: Optional[bool] = None,
        search: Optional[str] = None,
        location: Optional[str] = None,
        location_sub: Optional[str] = None,
        shot_type: Optional[str] = None,
        focal_class: Optional[str] = None,
        focal_mm: Optional[str] = None,
        aperture: Optional[str] = None,
        dof: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        light_temp: Optional[str] = None,
        light_intensity: Optional[str] = None,
        time_of_day: Optional[str] = None,
        stance: Optional[str] = None,
        gaze: Optional[str] = None,
        body_orientation: Optional[str] = None,
        expression: Optional[str] = None,
        archetype_tag: Optional[str] = None,
        aesthetic_tag: Optional[str] = None,
        material: Optional[str] = None,
        training_readiness: Optional[str] = None,
        training_lane_hint: Optional[str] = None,
        training_style_tag: Optional[str] = None,
        training_quality_flag: Optional[str] = None,
        identity_cluster_hint: Optional[str] = None,
        look_state_hint: Optional[str] = None,
    ):
        normalized_status = (analysis_status or "").strip().upper()
        normalized_search = (search or "").strip().lower()
        normalized_handle = None
        if source_handle:
            normalized_handle = (
                source_handle if source_handle.startswith("@") else f"@{source_handle}"
            )
        tag_set = set(tags or [])
        projection_filters = _build_projection_filters(
            location=location,
            location_sub=location_sub,
            shot_type=shot_type,
            focal_class=focal_class,
            focal_mm=focal_mm,
            aperture=aperture,
            dof=dof,
            aspect_ratio=aspect_ratio,
            light_temp=light_temp,
            light_intensity=light_intensity,
            time_of_day=time_of_day,
            stance=stance,
            gaze=gaze,
            body_orientation=body_orientation,
            expression=expression,
            archetype_tag=archetype_tag,
            aesthetic_tag=aesthetic_tag,
            material=material,
            training_readiness=training_readiness,
            training_lane_hint=training_lane_hint,
            training_style_tag=training_style_tag,
            training_quality_flag=training_quality_flag,
            identity_cluster_hint=identity_cluster_hint,
            look_state_hint=look_state_hint,
        )

        for entry in data.get("entries", {}).values():
            resolved_entry = _resolve_browsing_entry(entry)

            if resolved_entry.get("deleted") and not include_deleted:
                continue

            if normalized_handle and resolved_entry.get("source_handle") != normalized_handle:
                continue

            if tag_set:
                entry_tags = set(resolved_entry.get("tags", []) + resolved_entry.get("auto_tags", []))
                if not entry_tags.intersection(tag_set):
                    continue

            if collection and collection not in resolved_entry.get("collections", []):
                continue

            if project_id and resolved_entry.get("project_id") != project_id:
                continue

            if analysis_profile and resolved_entry.get("analysis_profile") != analysis_profile:
                continue

            if normalized_status and _resolved_browsing_status(resolved_entry) != normalized_status:
                continue

            if schema_version and resolved_entry.get("schema_version") != schema_version:
                continue

            if has_analysis is not None and resolved_entry.get("has_analysis", False) != has_analysis:
                continue

            if normalized_search:
                search_fields = list(_iter_searchable_entry_fields(resolved_entry))
                if not any(normalized_search in str(field).lower() for field in search_fields if field):
                    continue

            skip = False
            for field, value, match_type in projection_filters:
                entry_value = resolved_entry.get(field)
                if match_type == "exact":
                    if not entry_value or str(entry_value).strip().lower() != value:
                        skip = True
                        break
                elif match_type == "in_list":
                    entry_list = entry_value if isinstance(entry_value, list) else []
                    if value not in [str(item).strip().lower() for item in entry_list]:
                        skip = True
                        break
                elif match_type == "substring":
                    if not entry_value or value not in str(entry_value).lower():
                        skip = True
                        break
            if skip:
                continue

            yield resolved_entry

    def _sort_results(
        self,
        results: List[Dict[str, Any]],
        *,
        sort_by: Optional[str] = None,
        normalized_status: str = "",
    ) -> List[Dict[str, Any]]:
        sort_key = (sort_by or "analyzed_latest").strip().lower()
        if sort_key in {"pending_latest", "pending_oldest"} and not normalized_status:
            results = [entry for entry in results if _is_pending_queue_candidate(entry)]

        if sort_key == "newest":
            results.sort(key=lambda x: _sortable_timestamp(x.get("pinned_at")), reverse=True)
        elif sort_key == "oldest":
            results.sort(
                key=lambda x: (
                    _sortable_timestamp(x.get("pinned_at")) == "",
                    _sortable_timestamp(x.get("pinned_at")),
                )
            )
        elif sort_key == "pending_latest":
            results.sort(key=lambda x: _sortable_timestamp(x.get("pending_sort_at")), reverse=True)
        elif sort_key == "pending_oldest":
            results.sort(
                key=lambda x: (
                    _sortable_timestamp(x.get("pending_sort_at")) == "",
                    _sortable_timestamp(x.get("pending_sort_at")),
                )
            )
        elif sort_key == "analyzed_oldest":
            results.sort(
                key=lambda x: (
                    _sortable_timestamp(x.get("validated_at")) == "",
                    _sortable_timestamp(x.get("validated_at")),
                )
            )
        elif sort_key == "handle_az":
            results.sort(key=lambda x: _sortable_text(x.get("source_handle")).lower())
        elif sort_key == "handle_za":
            results.sort(key=lambda x: _sortable_text(x.get("source_handle")).lower(), reverse=True)
        elif sort_key == "status":
            results.sort(key=lambda x: _sortable_text(x.get("analysis_status")).lower())
        else:
            results.sort(key=lambda x: _sortable_timestamp(x.get("validated_at")), reverse=True)
        return results

    def query(
        self,
        source_handle: Optional[str] = None,
        tags: Optional[List[str]] = None,
        collection: Optional[str] = None,
        project_id: Optional[str] = None,
        include_deleted: bool = False,
        analysis_profile: Optional[str] = None,
        analysis_status: Optional[str] = None,
        schema_version: Optional[str] = None,
        has_analysis: Optional[bool] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        # --- V2.0 projection filters (Phase 1) ---
        location: Optional[str] = None,
        location_sub: Optional[str] = None,
        shot_type: Optional[str] = None,
        focal_class: Optional[str] = None,
        focal_mm: Optional[str] = None,
        aperture: Optional[str] = None,
        dof: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        light_temp: Optional[str] = None,
        light_intensity: Optional[str] = None,
        time_of_day: Optional[str] = None,
        stance: Optional[str] = None,
        gaze: Optional[str] = None,
        body_orientation: Optional[str] = None,
        expression: Optional[str] = None,
        archetype_tag: Optional[str] = None,
        aesthetic_tag: Optional[str] = None,
        material: Optional[str] = None,
        training_readiness: Optional[str] = None,
        training_lane_hint: Optional[str] = None,
        training_style_tag: Optional[str] = None,
        training_quality_flag: Optional[str] = None,
        identity_cluster_hint: Optional[str] = None,
        look_state_hint: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query references from index with support for V2.0 schema filters."""
        data = self._read_index()
        normalized_status = (analysis_status or "").strip().upper()
        results = list(
            self._iter_filtered_entries(
                data,
                source_handle=source_handle,
                tags=tags,
                collection=collection,
                project_id=project_id,
                include_deleted=include_deleted,
                analysis_profile=analysis_profile,
                analysis_status=analysis_status,
                schema_version=schema_version,
                has_analysis=has_analysis,
                search=search,
                location=location,
                location_sub=location_sub,
                shot_type=shot_type,
                focal_class=focal_class,
                focal_mm=focal_mm,
                aperture=aperture,
                dof=dof,
                aspect_ratio=aspect_ratio,
                light_temp=light_temp,
                light_intensity=light_intensity,
                time_of_day=time_of_day,
                stance=stance,
                gaze=gaze,
                body_orientation=body_orientation,
                expression=expression,
                archetype_tag=archetype_tag,
                aesthetic_tag=aesthetic_tag,
                material=material,
                training_readiness=training_readiness,
                training_lane_hint=training_lane_hint,
                training_style_tag=training_style_tag,
                training_quality_flag=training_quality_flag,
                identity_cluster_hint=identity_cluster_hint,
                look_state_hint=look_state_hint,
            )
        )
        return self._sort_results(
            results,
            sort_by=sort_by,
            normalized_status=normalized_status,
        )

    def query_facets(
        self,
        source_handle: Optional[str] = None,
        tags: Optional[List[str]] = None,
        collection: Optional[str] = None,
        project_id: Optional[str] = None,
        include_deleted: bool = False,
        analysis_profile: Optional[str] = None,
        analysis_status: Optional[str] = None,
        schema_version: Optional[str] = None,
        has_analysis: Optional[bool] = None,
        search: Optional[str] = None,
        # --- V2.0 projection filters (Phase 1) ---
        location: Optional[str] = None,
        location_sub: Optional[str] = None,
        shot_type: Optional[str] = None,
        focal_class: Optional[str] = None,
        focal_mm: Optional[str] = None,
        aperture: Optional[str] = None,
        dof: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        light_temp: Optional[str] = None,
        light_intensity: Optional[str] = None,
        time_of_day: Optional[str] = None,
        stance: Optional[str] = None,
        gaze: Optional[str] = None,
        body_orientation: Optional[str] = None,
        expression: Optional[str] = None,
        archetype_tag: Optional[str] = None,
        aesthetic_tag: Optional[str] = None,
        material: Optional[str] = None,
        training_readiness: Optional[str] = None,
        training_lane_hint: Optional[str] = None,
        training_style_tag: Optional[str] = None,
        training_quality_flag: Optional[str] = None,
        identity_cluster_hint: Optional[str] = None,
        look_state_hint: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        data = self._read_index()
        handle_counts: Dict[str, int] = {}
        for entry in self._iter_filtered_entries(
            data,
            source_handle=None,
            tags=tags,
            collection=collection,
            project_id=project_id,
            include_deleted=include_deleted,
            analysis_profile=analysis_profile,
            analysis_status=analysis_status,
            schema_version=schema_version,
            has_analysis=has_analysis,
            search=search,
            location=location,
            location_sub=location_sub,
            shot_type=shot_type,
            focal_class=focal_class,
            focal_mm=focal_mm,
            aperture=aperture,
            dof=dof,
            aspect_ratio=aspect_ratio,
            light_temp=light_temp,
            light_intensity=light_intensity,
            time_of_day=time_of_day,
            stance=stance,
            gaze=gaze,
            body_orientation=body_orientation,
            expression=expression,
            archetype_tag=archetype_tag,
            aesthetic_tag=aesthetic_tag,
            material=material,
            training_readiness=training_readiness,
            training_lane_hint=training_lane_hint,
            training_style_tag=training_style_tag,
            training_quality_flag=training_quality_flag,
            identity_cluster_hint=identity_cluster_hint,
            look_state_hint=look_state_hint,
        ):
            handle = str(entry.get("source_handle", "")).strip()
            if handle:
                handle_counts[handle] = handle_counts.get(handle, 0) + 1

        tag_counts: Dict[str, int] = {}
        for entry in self._iter_filtered_entries(
            data,
            source_handle=source_handle,
            tags=None,
            collection=collection,
            project_id=project_id,
            include_deleted=include_deleted,
            analysis_profile=analysis_profile,
            analysis_status=analysis_status,
            schema_version=schema_version,
            has_analysis=has_analysis,
            search=search,
            location=location,
            location_sub=location_sub,
            shot_type=shot_type,
            focal_class=focal_class,
            focal_mm=focal_mm,
            aperture=aperture,
            dof=dof,
            aspect_ratio=aspect_ratio,
            light_temp=light_temp,
            light_intensity=light_intensity,
            time_of_day=time_of_day,
            stance=stance,
            gaze=gaze,
            body_orientation=body_orientation,
            expression=expression,
            archetype_tag=archetype_tag,
            aesthetic_tag=aesthetic_tag,
            material=material,
            training_readiness=training_readiness,
            training_lane_hint=training_lane_hint,
            training_style_tag=training_style_tag,
            training_quality_flag=training_quality_flag,
            identity_cluster_hint=identity_cluster_hint,
            look_state_hint=look_state_hint,
        ):
            seen_tags = set()
            for tag in [*(entry.get("tags") or []), *(entry.get("auto_tags") or [])]:
                normalized = str(tag).strip()
                if not normalized or normalized in seen_tags:
                    continue
                seen_tags.add(normalized)
                tag_counts[normalized] = tag_counts.get(normalized, 0) + 1

        profile_counts: Dict[str, int] = {}
        for entry in self._iter_filtered_entries(
            data,
            source_handle=source_handle,
            tags=tags,
            collection=collection,
            project_id=project_id,
            include_deleted=include_deleted,
            analysis_profile=None,
            analysis_status=analysis_status,
            schema_version=schema_version,
            has_analysis=has_analysis,
            search=search,
            location=location,
            location_sub=location_sub,
            shot_type=shot_type,
            focal_class=focal_class,
            focal_mm=focal_mm,
            aperture=aperture,
            dof=dof,
            aspect_ratio=aspect_ratio,
            light_temp=light_temp,
            light_intensity=light_intensity,
            time_of_day=time_of_day,
            stance=stance,
            gaze=gaze,
            body_orientation=body_orientation,
            expression=expression,
            archetype_tag=archetype_tag,
            aesthetic_tag=aesthetic_tag,
            material=material,
            training_readiness=training_readiness,
            training_lane_hint=training_lane_hint,
            training_style_tag=training_style_tag,
            training_quality_flag=training_quality_flag,
            identity_cluster_hint=identity_cluster_hint,
            look_state_hint=look_state_hint,
        ):
            profile = str(entry.get("analysis_profile", "")).strip()
            if profile:
                profile_counts[profile] = profile_counts.get(profile, 0) + 1

        training_readiness_counts: Dict[str, int] = {}
        training_lane_hint_counts: Dict[str, int] = {}
        training_style_tag_counts: Dict[str, int] = {}
        training_quality_flag_counts: Dict[str, int] = {}
        identity_cluster_hint_counts: Dict[str, int] = {}
        look_state_hint_counts: Dict[str, int] = {}

        for entry in self._iter_filtered_entries(
            data,
            source_handle=source_handle,
            tags=tags,
            collection=collection,
            project_id=project_id,
            include_deleted=include_deleted,
            analysis_profile=analysis_profile,
            analysis_status=analysis_status,
            schema_version=schema_version,
            has_analysis=has_analysis,
            search=search,
            location=location,
            location_sub=location_sub,
            shot_type=shot_type,
            focal_class=focal_class,
            focal_mm=focal_mm,
            aperture=aperture,
            dof=dof,
            aspect_ratio=aspect_ratio,
            light_temp=light_temp,
            light_intensity=light_intensity,
            time_of_day=time_of_day,
            stance=stance,
            gaze=gaze,
            body_orientation=body_orientation,
            expression=expression,
            archetype_tag=archetype_tag,
            aesthetic_tag=aesthetic_tag,
            material=material,
        ):
            readiness = str(entry.get("p_training_readiness", "")).strip()
            if readiness:
                training_readiness_counts[readiness] = training_readiness_counts.get(readiness, 0) + 1

            for value, counter in (
                (entry.get("p_training_lane_hints", []), training_lane_hint_counts),
                (entry.get("p_training_style_tags", []), training_style_tag_counts),
                (entry.get("p_training_quality_flags", []), training_quality_flag_counts),
            ):
                for item in value if isinstance(value, list) else []:
                    normalized = str(item).strip()
                    if not normalized:
                        continue
                    counter[normalized] = counter.get(normalized, 0) + 1

            identity_hint = str(entry.get("p_training_identity_cluster_hint", "")).strip()
            if identity_hint:
                identity_cluster_hint_counts[identity_hint] = identity_cluster_hint_counts.get(identity_hint, 0) + 1

            look_hint = str(entry.get("p_training_look_state_hint", "")).strip()
            if look_hint:
                look_state_hint_counts[look_hint] = look_state_hint_counts.get(look_hint, 0) + 1

        source_handles = sorted(handle_counts)
        tag_values = sorted(tag_counts)
        profiles = sorted(profile_counts)
        training_readiness_values = sorted(training_readiness_counts)
        training_lane_hint_values = sorted(training_lane_hint_counts)
        training_style_tag_values = sorted(training_style_tag_counts)
        training_quality_flag_values = sorted(training_quality_flag_counts)
        identity_cluster_hint_values = sorted(identity_cluster_hint_counts)
        look_state_hint_values = sorted(look_state_hint_counts)

        return {
            "source_handles": source_handles,
            "tags": tag_values,
            "analysis_profiles": profiles,
            "training_readiness_values": training_readiness_values,
            "training_lane_hint_values": training_lane_hint_values,
            "training_style_tag_values": training_style_tag_values,
            "training_quality_flag_values": training_quality_flag_values,
            "identity_cluster_hint_values": identity_cluster_hint_values,
            "look_state_hint_values": look_state_hint_values,
            "source_handle_options": _build_counted_options(handle_counts),
            "tag_options": _build_counted_options(tag_counts),
            "analysis_profile_options": _build_counted_options(profile_counts),
            "training_readiness_options": _build_counted_options(training_readiness_counts),
            "training_lane_hint_options": _build_counted_options(training_lane_hint_counts),
            "training_style_tag_options": _build_counted_options(training_style_tag_counts),
            "training_quality_flag_options": _build_counted_options(training_quality_flag_counts),
            "identity_cluster_hint_options": _build_counted_options(identity_cluster_hint_counts),
            "look_state_hint_options": _build_counted_options(look_state_hint_counts),
        }

    def find_by_content_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """Find existing reference by content_hash (for deduplication)."""
        data = self._read_index()
        for entry in data.get("entries", {}).values():
            if entry.get("content_hash") == content_hash and not entry.get("deleted"):
                return entry
        return None

    def rebuild(self) -> Dict[str, Any]:
        """Full rebuild from filesystem scan (fallback).

        Scans all @handle/ and _unsorted/ directories for .json metadata files.
        """
        logger.info("[RefIndex] Rebuilding index from filesystem: %s", self.references_path)
        data = {"version": "1.0", "updated_at": _utc_now_iso(), "entries": {}}

        if not self.references_path.exists():
            return data

        for child in self.references_path.iterdir():
            if not child.is_dir():
                continue
            if child.name.startswith("_") and child.name != "_unsorted":
                continue

            # Scan .json metadata files
            for json_file in child.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                    ref_id = metadata.get("reference_id")
                    if ref_id:
                        entry = {
                            "reference_id": ref_id,
                            "content_hash": metadata.get("content_hash", ""),
                            "source_handle": metadata.get("source_handle", ""),
                            "source_shortcode": metadata.get("source_shortcode", ""),
                            "tags": metadata.get("tags", []),
                            "auto_tags": metadata.get("auto_tags", []),
                            "collections": metadata.get("collections", []),
                            "pinned_at": _normalize_timestamp_text(metadata.get("pinned_at", "")),
                            "deleted": metadata.get("deleted", False),
                            "has_analysis": metadata.get("vision_description") is not None,
                            "analysis_status": (
                                metadata.get("analysis_job", {}).get("status", "")
                                if metadata.get("analysis_job")
                                else ""
                            ),
                            "project_id": metadata.get("project_id", ""),
                            "analysis_profile": (
                                metadata.get("analysis_provenance", {}).get("analysis_profile", "")
                                if metadata.get("analysis_provenance") else ""
                            ),
                            "schema_version": (
                                metadata.get("analysis_provenance", {}).get("schema_version", "")
                                if metadata.get("analysis_provenance") else ""
                            ),
                            "queued_at": _extract_job_timestamp(metadata, "queued_at"),
                            "started_at": _extract_job_timestamp(metadata, "started_at"),
                            "validated_at": _extract_validated_at(metadata),
                            "pending_sort_at": _extract_pending_sort_at(metadata),
                            "analysis_error": (
                                metadata.get("analysis_job", {}).get("last_error", "")
                                if metadata.get("analysis_job") else ""
                            ),
                            "analysis_failure_stage": (
                                metadata.get("analysis_debug", {}).get("failure_stage", "")
                                if metadata.get("analysis_debug") else ""
                            ),
                            "analysis_excerpt": (
                                metadata.get("analysis_debug", {}).get("description_excerpt", "")
                                if metadata.get("analysis_debug") else ""
                            ),
                            "has_thinking": bool(
                                (metadata.get("analysis_debug") or {}).get("thinking_text")
                                or (metadata.get("vision_description") or {}).get("_thinking")
                            ),
                        }
                        # Merge V2.0 projection fields during rebuild
                        vision = metadata.get("vision_description")
                        if vision and isinstance(vision, dict):
                            entry.update(build_projection(vision))
                        data["entries"][ref_id] = entry
                except Exception as e:
                    logger.warning("[RefIndex] Failed to read %s: %s", json_file, e)

        # Write rebuilt index
        self._write_index(data)
        logger.info("[RefIndex] Rebuilt index with %d entries", len(data["entries"]))
        return data
