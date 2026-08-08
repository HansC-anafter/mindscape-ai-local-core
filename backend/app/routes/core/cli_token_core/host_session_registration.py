from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from backend.app.routes.core.cli_token_core.host_session_metadata import (
    _default_pool_group_for_surface,
    _stable_host_session_runtime_id,
)
from backend.app.routes.core.cli_token_core.host_session_shadow import (
    _list_host_session_shadow_candidates,
    _reconcile_host_session_runtime_shadow,
)
from backend.app.routes.core.cli_token_core.host_session_store import (
    _upsert_host_session_runtime,
)
from backend.app.routes.core.cli_token_core.schemas import RegisterHostSessionRuntimeRequest

_RUNTIME_REFRESH_SECONDS = 300.0
_RUNTIME_CACHE_MAX_ENTRIES = 256
_SHADOW_SNAPSHOT_MAX_ENTRIES = 128
_SHADOW_RECONCILIATION_MAX_ENTRIES = 1024
_SHADOW_SNAPSHOT_MAX_CANDIDATE_IDS = 1024

ShadowCandidateKey = tuple[str, str]
ShadowCandidateMap = Mapping[ShadowCandidateKey, tuple[str, ...]]


@dataclass(frozen=True)
class _RuntimeRegistrationEntry:
    fingerprint: str
    expires_at: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class _ShadowCandidateSnapshot:
    expires_at: float
    candidates: dict[ShadowCandidateKey, tuple[str, ...]]
    candidate_id_count: int


class HostSessionRegistrationCoordinator:
    def __init__(
        self,
        *,
        refresh_seconds: float = _RUNTIME_REFRESH_SECONDS,
        runtime_max_entries: int = _RUNTIME_CACHE_MAX_ENTRIES,
        shadow_snapshot_max_entries: int = _SHADOW_SNAPSHOT_MAX_ENTRIES,
        shadow_reconciliation_max_entries: int = _SHADOW_RECONCILIATION_MAX_ENTRIES,
        shadow_snapshot_max_candidate_ids: int = _SHADOW_SNAPSHOT_MAX_CANDIDATE_IDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if refresh_seconds <= 0:
            raise ValueError("refresh_seconds must be positive")
        for name, value in (
            ("runtime_max_entries", runtime_max_entries),
            ("shadow_snapshot_max_entries", shadow_snapshot_max_entries),
            ("shadow_reconciliation_max_entries", shadow_reconciliation_max_entries),
            ("shadow_snapshot_max_candidate_ids", shadow_snapshot_max_candidate_ids),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")

        self._refresh_seconds = float(refresh_seconds)
        self._runtime_max_entries = int(runtime_max_entries)
        self._shadow_snapshot_max_entries = int(shadow_snapshot_max_entries)
        self._shadow_reconciliation_max_entries = int(
            shadow_reconciliation_max_entries
        )
        self._shadow_snapshot_max_candidate_ids = int(
            shadow_snapshot_max_candidate_ids
        )
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._runtime_entries: OrderedDict[str, _RuntimeRegistrationEntry] = (
            OrderedDict()
        )
        self._shadow_snapshots: OrderedDict[str, _ShadowCandidateSnapshot] = (
            OrderedDict()
        )
        self._shadow_reconciliations: OrderedDict[str, float] = OrderedDict()

    @property
    def cache_sizes(self) -> dict[str, int]:
        with self._lock:
            return {
                "runtime": len(self._runtime_entries),
                "shadow_snapshot": len(self._shadow_snapshots),
                "shadow_candidate_ids": sum(
                    snapshot.candidate_id_count
                    for snapshot in self._shadow_snapshots.values()
                ),
                "shadow_reconciliation": len(self._shadow_reconciliations),
            }

    def clear(self) -> None:
        with self._lock:
            self._runtime_entries.clear()
            self._shadow_snapshots.clear()
            self._shadow_reconciliations.clear()

    @staticmethod
    def _bounded_set(
        entries: OrderedDict[str, Any],
        key: str,
        value: Any,
        *,
        max_entries: int,
    ) -> None:
        entries[key] = value
        entries.move_to_end(key)
        while len(entries) > max_entries:
            entries.popitem(last=False)

    @staticmethod
    def _normalize_semantic_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(dict(metadata or {}))
        for key in ("seed_last_seen_at", "last_workspace_id", "last_client_id"):
            normalized.pop(key, None)
        health = normalized.get("codex_pool_health")
        if isinstance(health, dict):
            health = dict(health)
            health.pop("last_seen_at", None)
            normalized["codex_pool_health"] = health
        return normalized

    @classmethod
    def _semantic_fingerprint(
        cls,
        *,
        owner_user_id: str,
        runtime_id: str,
        request: RegisterHostSessionRuntimeRequest,
    ) -> str:
        surface = str(request.surface or "").strip().lower()
        pool_group = request.pool_group or _default_pool_group_for_surface(surface)
        runtime_name = (
            str(request.runtime_name or "").strip() or f"{surface} host session"
        )
        semantic = {
            "owner_user_id": owner_user_id,
            "runtime_id": runtime_id,
            "surface": surface,
            "runtime_name": runtime_name,
            "pool_group": pool_group,
            "pool_enabled": bool(request.pool_enabled),
            "pool_priority": int(request.pool_priority),
            "metadata": cls._normalize_semantic_metadata(request.metadata),
        }
        serialized = json.dumps(
            semantic,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _shadow_group(
        *,
        owner_user_id: str,
        request: RegisterHostSessionRuntimeRequest,
    ) -> tuple[str, str, str] | None:
        metadata = dict(request.metadata or {})
        home = str(metadata.get("HOME") or "").strip()
        codex_home = str(metadata.get("CODEX_HOME") or "").strip()
        if not home or not codex_home:
            return None
        surface = str(request.surface or "").strip().lower()
        pool_group = str(
            request.pool_group or _default_pool_group_for_surface(surface) or ""
        ).strip()
        return owner_user_id, surface, pool_group

    @staticmethod
    def _shadow_candidate_key(
        request: RegisterHostSessionRuntimeRequest,
    ) -> ShadowCandidateKey:
        metadata = dict(request.metadata or {})
        return (
            str(metadata.get("HOME") or "").strip(),
            str(request.workspace_id or "").strip(),
        )

    @staticmethod
    def _cache_key(parts: tuple[str, ...]) -> str:
        return json.dumps(parts, ensure_ascii=True, separators=(",", ":"))

    def _invalidate_shadow_group(self, group_key: str) -> None:
        self._shadow_snapshots.pop(group_key, None)
        prefix = f"{group_key}:"
        for key in list(self._shadow_reconciliations):
            if key.startswith(prefix):
                self._shadow_reconciliations.pop(key, None)

    def _cache_shadow_snapshot(
        self,
        *,
        group_key: str,
        snapshot: _ShadowCandidateSnapshot,
    ) -> None:
        self._shadow_snapshots[group_key] = snapshot
        self._shadow_snapshots.move_to_end(group_key)
        while self._shadow_snapshots:
            total_candidate_ids = sum(
                item.candidate_id_count for item in self._shadow_snapshots.values()
            )
            if (
                len(self._shadow_snapshots) <= self._shadow_snapshot_max_entries
                and total_candidate_ids
                <= self._shadow_snapshot_max_candidate_ids
            ):
                break
            self._shadow_snapshots.popitem(last=False)

    def _load_shadow_snapshot(
        self,
        *,
        group: tuple[str, str, str],
        now: float,
        list_shadow_candidates: Callable[..., ShadowCandidateMap],
    ) -> dict[ShadowCandidateKey, tuple[str, ...]]:
        group_key = self._cache_key(group)
        cached = self._shadow_snapshots.get(group_key)
        if cached is not None and cached.expires_at > now:
            self._shadow_snapshots.move_to_end(group_key)
            return cached.candidates

        self._invalidate_shadow_group(group_key)
        owner_user_id, surface, pool_group = group
        loaded = list_shadow_candidates(
            owner_user_id=owner_user_id,
            surface=surface,
            pool_group=pool_group,
        )
        candidates = {
            (str(key[0]), str(key[1])): tuple(str(item) for item in runtime_ids)
            for key, runtime_ids in dict(loaded).items()
            if len(key) == 2 and runtime_ids
        }
        candidate_id_count = sum(len(runtime_ids) for runtime_ids in candidates.values())
        if candidate_id_count <= self._shadow_snapshot_max_candidate_ids:
            self._cache_shadow_snapshot(
                group_key=group_key,
                snapshot=_ShadowCandidateSnapshot(
                    expires_at=now + self._refresh_seconds,
                    candidates=candidates,
                    candidate_id_count=candidate_id_count,
                ),
            )
        return candidates

    @staticmethod
    def _localized_payload(
        payload: Mapping[str, Any],
        *,
        owner_user_id: str,
        request: RegisterHostSessionRuntimeRequest,
    ) -> dict[str, Any]:
        localized = copy.deepcopy(dict(payload))
        metadata = dict(localized.get("metadata") or {})
        metadata["last_workspace_id"] = request.workspace_id
        metadata["last_client_id"] = request.client_id
        seed_last_seen_at = (request.metadata or {}).get("seed_last_seen_at")
        if seed_last_seen_at is not None:
            metadata["seed_last_seen_at"] = seed_last_seen_at
        localized["metadata"] = metadata
        localized["owner_user_id"] = owner_user_id
        runtime_id = localized.get("runtime_id") or localized.get("id")
        if runtime_id:
            localized["runtime_id"] = runtime_id
        return localized

    def register(
        self,
        *,
        owner_user_id: str,
        request: RegisterHostSessionRuntimeRequest,
        upsert_runtime: Callable[..., dict[str, Any]] = _upsert_host_session_runtime,
        list_shadow_candidates: Callable[..., ShadowCandidateMap] = (
            _list_host_session_shadow_candidates
        ),
        reconcile_shadow: Callable[..., bool] = (
            _reconcile_host_session_runtime_shadow
        ),
    ) -> dict[str, Any]:
        runtime_id = _stable_host_session_runtime_id(
            owner_user_id=owner_user_id,
            surface=request.surface,
            client_id=request.client_id,
            metadata=request.metadata,
            workspace_id=request.workspace_id,
            explicit_runtime_id=request.runtime_id,
        )
        fingerprint = self._semantic_fingerprint(
            owner_user_id=owner_user_id,
            runtime_id=runtime_id,
            request=request,
        )

        with self._lock:
            now = self._monotonic()
            runtime_entry = self._runtime_entries.get(runtime_id)
            runtime_is_fresh = bool(
                runtime_entry is not None
                and runtime_entry.fingerprint == fingerprint
                and runtime_entry.expires_at > now
            )
            if runtime_is_fresh:
                self._runtime_entries.move_to_end(runtime_id)

            group = self._shadow_group(
                owner_user_id=owner_user_id,
                request=request,
            )
            shadow_runtime_ids: tuple[str, ...] = ()
            reconciliation_key = ""
            if group is not None:
                candidates = self._load_shadow_snapshot(
                    group=group,
                    now=now,
                    list_shadow_candidates=list_shadow_candidates,
                )
                candidate_key = self._shadow_candidate_key(request)
                shadow_runtime_ids = candidates.get(candidate_key, ())
                if shadow_runtime_ids:
                    group_key = self._cache_key(group)
                    reconciliation_key = (
                        f"{group_key}:{self._cache_key(candidate_key)}"
                    )
                    reconciled_until = self._shadow_reconciliations.get(
                        reconciliation_key,
                        0.0,
                    )
                    if reconciled_until > now:
                        shadow_runtime_ids = ()
                        self._shadow_reconciliations.move_to_end(reconciliation_key)

            if runtime_is_fresh:
                payload = runtime_entry.payload
            else:
                payload = upsert_runtime(
                    owner_user_id=owner_user_id,
                    request=request,
                    reconcile_shadow=False,
                )

            if shadow_runtime_ids:
                reconcile_shadow(
                    owner_user_id=owner_user_id,
                    request=request,
                    runtime_id=runtime_id,
                    candidate_runtime_ids=shadow_runtime_ids,
                )

            if not runtime_is_fresh:
                self._bounded_set(
                    self._runtime_entries,
                    runtime_id,
                    _RuntimeRegistrationEntry(
                        fingerprint=fingerprint,
                        expires_at=now + self._refresh_seconds,
                        payload=copy.deepcopy(payload),
                    ),
                    max_entries=self._runtime_max_entries,
                )
                if group is None:
                    surface = str(request.surface or "").strip().lower()
                    pool_group = str(
                        request.pool_group
                        or _default_pool_group_for_surface(surface)
                        or ""
                    ).strip()
                    self._invalidate_shadow_group(
                        self._cache_key((owner_user_id, surface, pool_group))
                    )

            if shadow_runtime_ids and reconciliation_key:
                self._bounded_set(
                    self._shadow_reconciliations,
                    reconciliation_key,
                    now + self._refresh_seconds,
                    max_entries=self._shadow_reconciliation_max_entries,
                )

            return self._localized_payload(
                payload,
                owner_user_id=owner_user_id,
                request=request,
            )


_HOST_SESSION_REGISTRATION_COORDINATOR = HostSessionRegistrationCoordinator()


def _register_host_session_runtime(
    *,
    owner_user_id: str,
    request: RegisterHostSessionRuntimeRequest,
) -> dict[str, Any]:
    return _HOST_SESSION_REGISTRATION_COORDINATOR.register(
        owner_user_id=owner_user_id,
        request=request,
    )
