"""Portable import and export helpers for composition graph drafts."""

from __future__ import annotations

from typing import Any, Dict

from backend.app.models.object_runtime import (
    CompositionGraphImportExportPayload,
    CompositionGraphNode,
)

SENSITIVE_EXPORT_KEYS = {
    "absolute_path",
    "artifact_dir",
    "db_row",
    "db_rows",
    "file_path",
    "local_absolute_path",
    "local_path",
    "raw_runtime_log",
    "runtime_log",
    "runtime_logs",
    "storage_path",
}


def sanitize_portable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitize_portable_value(item)
            for key, item in value.items()
            if str(key) not in SENSITIVE_EXPORT_KEYS
        }
    if isinstance(value, list):
        return [sanitize_portable_value(item) for item in value]
    return value


def sanitize_composition_graph_export_payload(
    payload: CompositionGraphImportExportPayload,
) -> CompositionGraphImportExportPayload:
    sanitized_nodes = [
        CompositionGraphNode(
            **{
                **node.model_dump(mode="json"),
                "payload": sanitize_portable_value(node.payload),
                "metadata": sanitize_portable_value(node.metadata),
            }
        )
        for node in payload.nodes
    ]
    return payload.model_copy(
        update={
            "nodes": sanitized_nodes,
            "metadata": sanitize_portable_value(payload.metadata),
        }
    )
