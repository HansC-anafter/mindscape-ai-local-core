"""Install-time runtime object catalog registry for installed packs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ObjectCatalogSyncResult:
    """Outcome from syncing runtime object catalog rows for a single pack."""

    changed: bool
    registry_path: Path
    object_count: int


class ObjectCatalogRegistry:
    """Persist normalized object-lane declarations for installed packs."""

    def __init__(self, local_core_root: Path):
        self.local_core_root = Path(local_core_root)
        self.runtime_object_catalog_root = self.local_core_root / "data" / "runtime_object_catalog"
        self.registry_path = self.runtime_object_catalog_root / "registry.json"

    def sync_pack_objects(
        self,
        capability_code: str,
        manifest: Dict[str, Any],
    ) -> ObjectCatalogSyncResult:
        """Rewrite the runtime object catalog for one installed pack."""
        previous_registry = self._load_registry()
        exports = self._normalize_object_exports(capability_code, manifest)
        next_registry = {
            "version": 1,
            "objects": [
                entry
                for entry in previous_registry.get("objects", [])
                if entry.get("owner_pack") != capability_code
            ]
            + exports,
        }
        next_registry["objects"] = sorted(
            next_registry["objects"],
            key=lambda entry: (
                entry.get("owner_pack", ""),
                entry.get("object_kind", ""),
                entry.get("display_name", ""),
            ),
        )

        changed = previous_registry != next_registry
        self.runtime_object_catalog_root.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(next_registry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return ObjectCatalogSyncResult(
            changed=changed,
            registry_path=self.registry_path,
            object_count=len(next_registry["objects"]),
        )

    def read_registry(self) -> Dict[str, Any]:
        """Return the persisted runtime object catalog payload."""
        return self._load_registry()

    def list_entries(
        self,
        *,
        owner_pack: Optional[str] = None,
        object_kind: Optional[str] = None,
        supports: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List normalized catalog entries with optional filters."""
        entries = list(self._load_registry().get("objects", []))

        if owner_pack:
            entries = [
                entry for entry in entries if entry.get("owner_pack") == owner_pack
            ]
        if object_kind:
            entries = [
                entry for entry in entries if entry.get("object_kind") == object_kind
            ]
        if supports:
            entries = [
                entry for entry in entries if supports in (entry.get("supports") or [])
            ]

        return entries

    def get_entry(self, owner_pack: str, object_kind: str) -> Optional[Dict[str, Any]]:
        """Return one normalized catalog entry for the given pack/object kind."""
        for entry in self._load_registry().get("objects", []):
            if (
                entry.get("owner_pack") == owner_pack
                and entry.get("object_kind") == object_kind
            ):
                return entry
        return None

    def get_catalog_version(self) -> str:
        """Return a runtime-friendly catalog version token."""
        if not self.registry_path.exists():
            return "1970-01-01T00:00:00Z"
        timestamp = datetime.fromtimestamp(
            self.registry_path.stat().st_mtime, tz=timezone.utc
        )
        return timestamp.isoformat().replace("+00:00", "Z")

    def _load_registry(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            return {"version": 1, "objects": []}
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "Failed to parse runtime object catalog registry %s: %s; rebuilding",
                self.registry_path,
                exc,
            )
            return {"version": 1, "objects": []}

    def _normalize_object_exports(
        self,
        capability_code: str,
        manifest: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        exports = manifest.get("object_exports", []) or []
        resolvers_by_kind = self._index_first_by_kind(manifest.get("object_resolvers", []) or [])
        meeting_projections_by_kind = self._index_many_by_kind(
            manifest.get("meeting_projections", []) or []
        )
        materializers_by_kind = self._index_many_by_kind(manifest.get("materializers", []) or [])
        graph_projections_by_kind = self._index_many_by_kind(
            manifest.get("graph_projections", []) or []
        )
        affordances = manifest.get("affordances", []) or []

        normalized: List[Dict[str, Any]] = []
        for index, export in enumerate(exports):
            if not isinstance(export, dict):
                logger.warning(
                    "[%s] Ignoring malformed object export at index %s: %r",
                    capability_code,
                    index,
                    export,
                )
                continue

            kind = str(export.get("kind", "")).strip()
            display_name = str(export.get("display_name", "")).strip()
            id_field = str(export.get("id_field", "")).strip()
            if not kind or not display_name or not id_field:
                logger.warning(
                    "[%s] Ignoring incomplete object export %r",
                    capability_code,
                    export,
                )
                continue

            resolver = resolvers_by_kind.get(kind, {})
            meeting_projections = meeting_projections_by_kind.get(kind, [])
            materializers = materializers_by_kind.get(kind, [])
            graph_projections = graph_projections_by_kind.get(kind, [])

            normalized.append(
                {
                    "owner_pack": capability_code,
                    "object_kind": kind,
                    "display_name": display_name,
                    "canonical_schema": self._clean_optional_str(export.get("canonical_schema")),
                    "id_field": id_field,
                    "summary_fields": self._clean_str_list(export.get("summary_fields")),
                    "supports": self._clean_str_list(export.get("supports")),
                    "granularity": self._clean_optional_str(export.get("granularity")),
                    "selector_families": self._clean_str_list(
                        export.get("selector_families")
                    ),
                    "indexer_backend": self._clean_optional_str(
                        export.get("indexer_backend")
                    ),
                    "mention_fields": self._clean_str_list(export.get("mention_fields")),
                    "owner_surface_patterns": self._clean_str_list(
                        export.get("owner_surface_patterns")
                    ),
                    "resolver_capabilities": {
                        "summary": bool(self._clean_optional_str(resolver.get("summary_backend"))),
                        "detail": bool(self._clean_optional_str(resolver.get("detail_backend"))),
                        "relations": bool(
                            self._clean_optional_str(resolver.get("relations_backend"))
                        ),
                        "actions": bool(self._clean_optional_str(resolver.get("actions_backend"))),
                    },
                    "resolver_backends": {
                        "summary_backend": self._clean_optional_str(
                            resolver.get("summary_backend")
                        ),
                        "detail_backend": self._clean_optional_str(
                            resolver.get("detail_backend")
                        ),
                        "relations_backend": self._clean_optional_str(
                            resolver.get("relations_backend")
                        ),
                        "actions_backend": self._clean_optional_str(
                            resolver.get("actions_backend")
                        ),
                    },
                    "meeting_projection_capabilities": {
                        "available": bool(meeting_projections),
                        "verbs": sorted(
                            {
                                verb
                                for projection in meeting_projections
                                for verb in self._clean_str_list(projection.get("verbs"))
                            }
                        ),
                    },
                    "meeting_projection_backends": [
                        {
                            "projection_backend": self._clean_optional_str(
                                projection.get("projection_backend")
                            ),
                            "projection_schema": self._clean_optional_str(
                                projection.get("projection_schema")
                            ),
                            "verbs": self._clean_str_list(projection.get("verbs")),
                        }
                        for projection in meeting_projections
                    ],
                    "materializer_capabilities": {
                        "available": bool(materializers),
                        "verbs": sorted(
                            {
                                verb
                                for materializer in materializers
                                for verb in self._clean_str_list(materializer.get("verbs"))
                            }
                        ),
                        "write_modes": sorted(
                            {
                                write_mode
                                for write_mode in (
                                    self._clean_optional_str(materializer.get("write_mode"))
                                    for materializer in materializers
                                )
                                if write_mode
                            }
                        ),
                        "output_types": sorted(
                            {
                                output_type
                                for materializer in materializers
                                for output_type in self._clean_str_list(
                                    materializer.get("output_types")
                                )
                            }
                        ),
                    },
                    "materializer_backends": [
                        {
                            "backend": self._clean_optional_str(materializer.get("backend")),
                            "verbs": self._clean_str_list(materializer.get("verbs")),
                            "output_types": self._clean_str_list(
                                materializer.get("output_types")
                            ),
                            "write_mode": self._clean_optional_str(
                                materializer.get("write_mode")
                            ),
                        }
                        for materializer in materializers
                    ],
                    "graph_projection_capabilities": {
                        "available": bool(graph_projections),
                        "node_kinds": sorted(
                            {
                                node_kind
                                for node_kind in (
                                    self._clean_optional_str(graph_projection.get("node_kind"))
                                    for graph_projection in graph_projections
                                )
                                if node_kind
                            }
                        ),
                        "relation_kinds": sorted(
                            {
                                relation_kind
                                for graph_projection in graph_projections
                                for relation_kind in self._clean_str_list(
                                    graph_projection.get("relation_kinds")
                                )
                            }
                        ),
                    },
                    "graph_projection_backends": [
                        {
                            "backend": self._clean_optional_str(graph_projection.get("backend")),
                            "node_kind": self._clean_optional_str(
                                graph_projection.get("node_kind")
                            ),
                            "relation_kinds": self._clean_str_list(
                                graph_projection.get("relation_kinds")
                            ),
                        }
                        for graph_projection in graph_projections
                    ],
                    "affordances": self._normalize_affordances_for_kind(
                        kind,
                        affordances,
                    ),
                }
            )

        return normalized

    @staticmethod
    def _index_first_by_kind(entries: List[Any]) -> Dict[str, Dict[str, Any]]:
        indexed: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            kind = str(entry.get("kind", "")).strip()
            if kind and kind not in indexed:
                indexed[kind] = entry
        return indexed

    @staticmethod
    def _index_many_by_kind(entries: List[Any]) -> Dict[str, List[Dict[str, Any]]]:
        indexed: Dict[str, List[Dict[str, Any]]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            kind = str(entry.get("kind", "")).strip()
            if not kind:
                continue
            indexed.setdefault(kind, []).append(entry)
        return indexed

    def _normalize_affordances_for_kind(
        self,
        kind: str,
        affordances: List[Any],
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for affordance in affordances:
            if not isinstance(affordance, dict):
                continue
            object_kinds = self._clean_str_list(affordance.get("object_kinds"))
            if object_kinds and kind not in object_kinds:
                continue
            verb = self._clean_optional_str(affordance.get("verb"))
            planner_backend = self._clean_optional_str(affordance.get("planner_backend"))
            if not verb or not planner_backend:
                continue
            input_schema = affordance.get("input_schema")
            output_schema = affordance.get("output_schema")
            normalized.append(
                {
                    "verb": verb,
                    "label": self._clean_optional_str(affordance.get("label")),
                    "description": self._clean_optional_str(
                        affordance.get("description")
                    ),
                    "object_kinds": object_kinds,
                    "input_schema": input_schema if isinstance(input_schema, dict) else {},
                    "output_schema": output_schema
                    if isinstance(output_schema, dict)
                    else {},
                    "required_roles": self._clean_str_list(
                        affordance.get("required_roles")
                    ),
                    "write_modes": self._clean_str_list(affordance.get("write_modes")),
                    "planner_backend": planner_backend,
                    "executor_backend": self._clean_optional_str(
                        affordance.get("executor_backend")
                    ),
                }
            )
        return sorted(
            normalized,
            key=lambda entry: (
                entry.get("verb", ""),
                ",".join(entry.get("object_kinds") or []),
            ),
        )

    @staticmethod
    def _clean_optional_str(value: Any) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _clean_str_list(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        return [text for text in (str(value).strip() for value in values) if text]
