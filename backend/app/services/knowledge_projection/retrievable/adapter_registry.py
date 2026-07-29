"""Exact, pack-neutral registry for active installed projection descriptors."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Mapping, Optional

from .adapter_descriptor import KnowledgeProjectionAdapterDescriptor
from .canonical_json import canonical_sha256


class KnowledgeProjectionAdapterRegistry:
    """Installed descriptor index with no known-pack or prefix fallback."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_capability: dict[
            str,
            dict[str, KnowledgeProjectionAdapterDescriptor],
        ] = {}

    def register_manifest(
        self,
        capability_code: str,
        manifest: Mapping[str, Any],
        capability_dir: Path,
    ) -> tuple[KnowledgeProjectionAdapterDescriptor, ...]:
        normalized_code = str(capability_code or "").strip()
        if not normalized_code or normalized_code != str(manifest.get("code") or "").strip():
            raise ValueError("knowledge_projection_manifest_capability_mismatch")
        capability_version = str(manifest.get("version") or "").strip()
        raw_entries = manifest.get("knowledge_projections")
        if raw_entries is None:
            raw_entries = []
        if not isinstance(raw_entries, list):
            raise ValueError("knowledge_projections_manifest_must_be_array")
        manifest_hash = canonical_sha256(manifest)
        exported_kinds = {
            str(item.get("kind") or "").strip()
            for item in manifest.get("object_exports") or ()
            if isinstance(item, Mapping)
        }
        registered: dict[str, KnowledgeProjectionAdapterDescriptor] = {}
        for raw in raw_entries:
            if not isinstance(raw, Mapping):
                raise ValueError("knowledge_projection_descriptor_must_be_mapping")
            descriptor = KnowledgeProjectionAdapterDescriptor.from_manifest_entry(
                capability_code=normalized_code,
                capability_version=capability_version,
                manifest_hash=manifest_hash,
                capability_dir=Path(capability_dir),
                raw=raw,
            )
            if any(kind not in exported_kinds for kind in descriptor.object_kinds):
                raise ValueError("knowledge_projection_object_kind_not_exported")
            if descriptor.descriptor_id in registered:
                raise ValueError("knowledge_projection_descriptor_id_duplicate")
            registered[descriptor.descriptor_id] = descriptor
        with self._lock:
            self._by_capability[normalized_code] = registered
        return tuple(registered[key] for key in sorted(registered))

    def unregister_capability(self, capability_code: str) -> None:
        with self._lock:
            self._by_capability.pop(str(capability_code or "").strip(), None)

    def resolve(
        self,
        *,
        capability_code: str,
        capability_version: str,
        descriptor_id: str,
        descriptor_hash: str,
        manifest_hash: str,
    ) -> KnowledgeProjectionAdapterDescriptor:
        with self._lock:
            descriptor = self._by_capability.get(capability_code, {}).get(descriptor_id)
        if descriptor is None:
            raise LookupError("knowledge_projection_descriptor_not_installed")
        if descriptor.capability_version != capability_version:
            raise LookupError("knowledge_projection_capability_version_mismatch")
        if descriptor.manifest_hash != manifest_hash:
            raise LookupError("knowledge_projection_manifest_hash_mismatch")
        if descriptor.descriptor_hash != descriptor_hash:
            raise LookupError("knowledge_projection_descriptor_hash_mismatch")
        return descriptor

    def list_capability(
        self,
        capability_code: str,
    ) -> tuple[KnowledgeProjectionAdapterDescriptor, ...]:
        with self._lock:
            entries = dict(self._by_capability.get(capability_code, {}))
        return tuple(entries[key] for key in sorted(entries))

    def reset_for_tests(self) -> None:
        with self._lock:
            self._by_capability.clear()


_REGISTRY = KnowledgeProjectionAdapterRegistry()


def get_adapter_registry() -> KnowledgeProjectionAdapterRegistry:
    return _REGISTRY


def register_manifest(
    capability_code: str,
    manifest: Mapping[str, Any],
    capability_dir: Path,
) -> tuple[KnowledgeProjectionAdapterDescriptor, ...]:
    return _REGISTRY.register_manifest(capability_code, manifest, capability_dir)


def resolve_descriptor(
    *,
    capability_code: str,
    capability_version: str,
    descriptor_id: str,
    descriptor_hash: str,
    manifest_hash: str,
) -> KnowledgeProjectionAdapterDescriptor:
    return _REGISTRY.resolve(
        capability_code=capability_code,
        capability_version=capability_version,
        descriptor_id=descriptor_id,
        descriptor_hash=descriptor_hash,
        manifest_hash=manifest_hash,
    )


def reset_registry_for_tests() -> None:
    _REGISTRY.reset_for_tests()
