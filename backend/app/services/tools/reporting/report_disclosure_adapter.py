"""Report-only mapping between a dependency graph and the neutral host port."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import dataclass
from typing import Any, BinaryIO, Mapping, Sequence

from backend.app.core.ports.artifact_disclosure import (
    ArtifactDisclosureDecision,
    ArtifactDisclosureItem,
    ArtifactDisclosurePort,
    ArtifactDisclosureRequest,
    ArtifactDisclosureReview,
    ArtifactDisclosureTarget,
    ArtifactProvenanceRef,
    DisclosureClassification,
    DisclosureScope,
)
from backend.app.services.tools.reporting.report_bundle_graph import (
    BundleSourceFile,
    ReportBundleGraph,
)
from backend.app.services.unified_tool_executor_core.governance_context import (
    VerifiedToolExecutionContext,
)
from backend.app.services.workspace_groups.shared_asset_scope_resolver import (
    SharedAssetScopeResolver,
)


_CLASSIFICATIONS = {
    "public",
    "internal",
    "confidential",
    "restricted",
    "unknown_binary",
}


@dataclass(frozen=True)
class ReportBundleDisclosureFile:
    source_file: BundleSourceFile
    archive_path: str
    classification: DisclosureClassification
    action: str
    output_sha256: str
    output_bytes: int
    finding_counts: tuple[tuple[str, int], ...]
    transformed_content: bytes | None
    transformed_content_file: BinaryIO | None = None

    @property
    def output_size(self) -> int:
        return self.output_bytes


@dataclass(frozen=True)
class ReportBundleDisclosurePlan:
    graph: ReportBundleGraph
    decision: ArtifactDisclosureDecision
    files: tuple[ReportBundleDisclosureFile, ...]

    @property
    def can_package(self) -> bool:
        return self.decision.can_disclose


class WorkspaceReportDisclosureAdapter:
    """The only report-domain adapter for the neutral disclosure port."""

    def __init__(
        self,
        *,
        disclosure_port: ArtifactDisclosurePort,
        shared_scope_resolver: SharedAssetScopeResolver | None = None,
    ) -> None:
        self._port = disclosure_port
        self._shared_scopes = (
            shared_scope_resolver or SharedAssetScopeResolver()
        )

    def evaluate(
        self,
        *,
        graph: ReportBundleGraph,
        governance_context: VerifiedToolExecutionContext,
        distribution_scope: DisclosureScope,
        recipient_ref: str | None,
        provenance_manifest: Any = None,
        disclosure_review: Any = None,
    ) -> ReportBundleDisclosurePlan:
        provenance = self._resolve_provenance(
            graph=graph,
            governance_context=governance_context,
            provenance_manifest=provenance_manifest,
            distribution_scope=distribution_scope,
        )
        items = tuple(
            ArtifactDisclosureItem(
                item_id=source_file.sandbox_relative_path,
                source_ref=source_file.sandbox_relative_path,
                source_path=source_file.path,
                analysis_file=source_file.analysis_file,
                source_sha256=source_file.sha256,
                source_bytes=source_file.size,
                media_type=(
                    mimetypes.guess_type(
                        source_file.sandbox_relative_path
                    )[0]
                    or "application/octet-stream"
                ),
                provenance=provenance[source_file.sandbox_relative_path][0],
                declared_classification=provenance[
                    source_file.sandbox_relative_path
                ][1],
            )
            for source_file in graph.files
        )
        artifact_set_sha256 = _artifact_set_sha256(items)
        request = ArtifactDisclosureRequest(
            authority=governance_context.to_artifact_disclosure_authority(),
            artifact_set_sha256=artifact_set_sha256,
            items=items,
            target=ArtifactDisclosureTarget(
                scope=distribution_scope,
                recipient_ref=_optional_string(recipient_ref),
            ),
            policy=self._port.policy_ref,
            review=_parse_review(disclosure_review),
        )
        decision = self._port.evaluate(request)
        by_id = {
            item.item_id: item for item in decision.item_decisions
        }
        files = tuple(
            ReportBundleDisclosureFile(
                source_file=source_file,
                archive_path=graph.archive_path_for(source_file),
                classification=by_id[
                    source_file.sandbox_relative_path
                ].classification,
                action=by_id[source_file.sandbox_relative_path].action,
                output_sha256=by_id[
                    source_file.sandbox_relative_path
                ].output_sha256,
                output_bytes=by_id[
                    source_file.sandbox_relative_path
                ].output_bytes,
                finding_counts=tuple(
                    (finding.code, finding.count)
                    for finding in by_id[
                        source_file.sandbox_relative_path
                    ].findings
                ),
                transformed_content=by_id[
                    source_file.sandbox_relative_path
                ].transformed_content,
                transformed_content_file=by_id[
                    source_file.sandbox_relative_path
                ].transformed_content_file,
            )
            for source_file in graph.files
        )
        return ReportBundleDisclosurePlan(
            graph=graph,
            decision=decision,
            files=files,
        )

    def _resolve_provenance(
        self,
        *,
        graph: ReportBundleGraph,
        governance_context: VerifiedToolExecutionContext,
        provenance_manifest: Any,
        distribution_scope: DisclosureScope,
    ) -> dict[
        str,
        tuple[ArtifactProvenanceRef, DisclosureClassification | None],
    ]:
        records = _parse_manifest_records(provenance_manifest)
        graph_paths = {
            source_file.sandbox_relative_path for source_file in graph.files
        }
        if records is not None and set(records) != graph_paths:
            raise ValueError("provenance_manifest_graph_mismatch")
        if records is None:
            if distribution_scope == "workspace_group":
                raise ValueError("workspace_group_provenance_required")
            return {
                path: (
                    ArtifactProvenanceRef(
                        origin="workspace_owned",
                        source_workspace_id=governance_context.workspace_id,
                        active_workspace_owner_user_id=(
                            governance_context.workspace_owner_user_id
                        ),
                    ),
                    None,
                )
                for path in graph_paths
            }

        group_records = [
            record
            for record in records.values()
            if record.get("origin") == "workspace_group_shared"
        ]
        resolution = None
        if group_records:
            group_ids = {
                _required_string(record, "group_id")
                for record in group_records
            }
            if len(group_ids) != 1:
                raise ValueError("provenance_group_id_mismatch")
            resolution = self._shared_scopes.resolve(
                workspace_id=governance_context.workspace_id,
                actor_user_id=governance_context.actor_user_id,
                allowed_workspace_ids=(
                    governance_context.allowed_workspace_ids
                ),
                allowed_group_ids=governance_context.allowed_group_ids,
                group_id=next(iter(group_ids)),
            )

        result = {}
        graph_by_path = {
            source_file.sandbox_relative_path: source_file
            for source_file in graph.files
        }
        for path, record in records.items():
            source_file = graph_by_path[path]
            if _required_string(record, "source_sha256") != source_file.sha256:
                raise ValueError("provenance_source_hash_mismatch")
            declared = _declared_classification(record)
            origin = record.get("origin")
            if origin == "workspace_owned":
                source_workspace_id = _required_string(
                    record,
                    "source_workspace_id",
                )
                if source_workspace_id != governance_context.workspace_id:
                    raise ValueError("workspace_provenance_mismatch")
                result[path] = (
                    ArtifactProvenanceRef(
                        origin="workspace_owned",
                        source_workspace_id=source_workspace_id,
                        active_workspace_owner_user_id=(
                            governance_context.workspace_owner_user_id
                        ),
                    ),
                    declared,
                )
                continue
            if origin != "workspace_group_shared" or resolution is None:
                raise ValueError("provenance_origin_invalid")
            scope = _match_shared_scope(
                record,
                resolution.scopes,
            )
            if (
                _required_string(record, "scope_fingerprint")
                != resolution.scope_fingerprint
            ):
                raise ValueError("provenance_scope_fingerprint_mismatch")
            result[path] = (
                ArtifactProvenanceRef(
                    origin="workspace_group_shared",
                    source_workspace_id=scope.source_workspace_id,
                    active_workspace_owner_user_id=(
                        scope.active_workspace_owner_user_id or ""
                    ),
                    group_id=scope.group_id,
                    group_owner_user_id=scope.group_owner_user_id,
                    source_workspace_owner_user_id=(
                        scope.source_workspace_owner_user_id
                    ),
                    binding_id=scope.binding_id,
                    resource_id=scope.resource_id,
                    group_revision=scope.group_revision,
                    scope_fingerprint=resolution.scope_fingerprint,
                ),
                declared,
            )
        return result


def _parse_manifest_records(
    payload: Any,
) -> dict[str, Mapping[str, Any]] | None:
    if payload is None:
        return None
    if isinstance(payload, Mapping):
        payload = payload.get("files")
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise ValueError("provenance_manifest_files_required")
    records: dict[str, Mapping[str, Any]] = {}
    for raw in payload:
        if not isinstance(raw, Mapping):
            raise ValueError("provenance_manifest_record_invalid")
        path = _required_string(raw, "source_path")
        if path in records:
            raise ValueError("provenance_manifest_duplicate_path")
        records[path] = raw
    return records


def _match_shared_scope(record, scopes):
    matches = [
        scope
        for scope in scopes
        if scope.binding_id == _required_string(record, "binding_id")
        and scope.resource_id == _required_string(record, "resource_id")
        and scope.source_workspace_id
        == _required_string(record, "source_workspace_id")
        and scope.group_id == _required_string(record, "group_id")
        and scope.group_revision == record.get("group_revision")
    ]
    if len(matches) != 1:
        raise ValueError("provenance_shared_scope_not_authorized")
    return matches[0]


def _declared_classification(
    record: Mapping[str, Any],
) -> DisclosureClassification | None:
    value = record.get("declared_classification")
    if value is None:
        return None
    if value not in _CLASSIFICATIONS:
        raise ValueError("declared_classification_invalid")
    return value


def _parse_review(payload: Any) -> ArtifactDisclosureReview | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise ValueError("disclosure_review_invalid")
    return ArtifactDisclosureReview(
        binding_sha256=_required_string(payload, "binding_sha256"),
        acknowledgement=_required_string(payload, "acknowledgement"),
    )


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}_required")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _artifact_set_sha256(
    items: tuple[ArtifactDisclosureItem, ...],
) -> str:
    payload = json.dumps(
        [
            {
                "item_id": item.item_id,
                "source_sha256": item.source_sha256,
                "source_bytes": item.source_bytes,
            }
            for item in items
        ],
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "ReportBundleDisclosureFile",
    "ReportBundleDisclosurePlan",
    "WorkspaceReportDisclosureAdapter",
]
