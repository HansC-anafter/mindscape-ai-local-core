"""Builtin workspace report share bundle tool."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.reporting.report_disclosure_adapter import (
    WorkspaceReportDisclosureAdapter,
)
from backend.app.services.tools.reporting.report_disclosure_composition import (
    build_workspace_report_disclosure_adapter,
)
from backend.app.services.tools.reporting.report_bundle_archive import (
    write_report_bundle_archive,
)
from backend.app.services.tools.reporting.report_bundle_graph import (
    MAX_BUNDLE_FILES,
    MAX_BUNDLE_SOURCE_BYTES,
    collect_report_bundle_graph,
)
from backend.app.services.tools.reporting.workspace_reporting_paths import (
    contains_symlink,
    is_relative_to,
    resolve_sandbox_relative_path,
    resolve_workspace_sandbox,
    validate_relative_path,
)
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolInputSchema,
    ToolMetadata,
)
from backend.app.services.unified_tool_executor_core.governance_context import (
    VerifiedToolExecutionContext,
)


DEFAULT_BUNDLE_SUBDIR = "reports/shared"
MISSING_REFERENCE_POLICIES = {"error", "record"}
OPERATIONS = {"package", "preflight"}
DISTRIBUTION_SCOPES = {"workspace", "workspace_group", "external"}


def _validate_report_path(report_path: str) -> PurePosixPath:
    path = validate_relative_path(
        report_path,
        field_name="report_path",
    )
    if path.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("report_path must end with .html or .htm")
    return path


def _validate_archive_name(
    archive_name: Optional[str],
    report_path: PurePosixPath,
) -> str:
    default_name = f"{report_path.stem}-share.zip"
    value = (archive_name or default_name).strip()
    if (
        not value
        or value != PurePosixPath(value).name
        or "\\" in value
    ):
        raise ValueError("archive_name must be a single file name")
    if not value.lower().endswith(".zip"):
        raise ValueError("archive_name must end with .zip")
    return value


def _validate_missing_reference_policy(policy: str) -> str:
    normalized = (policy or "error").strip().lower()
    if normalized not in MISSING_REFERENCE_POLICIES:
        raise ValueError(
            "missing_reference_policy must be error or record"
        )
    return normalized


class WorkspaceReportBundleTool(MindscapeTool):
    """Package one workspace HTML report and local dependencies into a ZIP."""

    def __init__(
        self,
        disclosure_adapter: WorkspaceReportDisclosureAdapter | None = None,
    ) -> None:
        metadata = ToolMetadata(
            name="workspace_package_report",
            description=(
                "Package a workspace HTML report and its bounded local linked "
                "files into a deterministic shareable ZIP with a hash manifest."
            ),
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "report_path": {
                        "type": "string",
                        "description": (
                            "Sandbox-relative .html report path to package"
                        ),
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": (
                            "Workspace identifier used with DATA_DIR/workspaces"
                        ),
                    },
                    "sandbox_path": {
                        "type": "string",
                        "description": (
                            "Absolute sandbox root under DATA_DIR/workspaces"
                        ),
                    },
                    "archive_name": {
                        "type": "string",
                        "description": (
                            "Optional single .zip output file name"
                        ),
                    },
                    "output_subdir": {
                        "type": "string",
                        "description": (
                            "Safe relative output directory inside the sandbox"
                        ),
                        "default": DEFAULT_BUNDLE_SUBDIR,
                    },
                    "include_linked_files": {
                        "type": "boolean",
                        "description": (
                            "Include bounded local HTML and CSS dependencies"
                        ),
                        "default": True,
                    },
                    "missing_reference_policy": {
                        "type": "string",
                        "enum": ["error", "record"],
                        "description": (
                            "Fail on missing local references or record a "
                            "partial bundle"
                        ),
                        "default": "error",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Overwrite an existing bundle",
                        "default": False,
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["package", "preflight"],
                        "default": "package",
                    },
                    "distribution_scope": {
                        "type": "string",
                        "enum": [
                            "workspace",
                            "workspace_group",
                            "external",
                        ],
                        "default": "workspace",
                    },
                    "recipient_ref": {
                        "type": "string",
                        "description": (
                            "Opaque recipient scope reference; never authority"
                        ),
                    },
                    "provenance_manifest": {
                        "type": "object",
                        "description": (
                            "Exact per-file source and classification evidence"
                        ),
                    },
                    "disclosure_review": {
                        "type": "object",
                        "description": (
                            "Verified-owner acknowledgement bound to preflight"
                        ),
                    },
                },
                required=["report_path"],
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="workspace_reporting",
            danger_level="medium",
            execution_timeout_seconds=90,
            tags=[
                "meeting_engine",
                "agent",
                "mcp",
                "reporting",
                "archive",
                "workspace",
            ],
        )
        super().__init__(metadata)
        self._disclosure_adapter = (
            disclosure_adapter
            or build_workspace_report_disclosure_adapter()
        )

    async def execute(
        self,
        report_path: str,
        workspace_id: Optional[str] = None,
        sandbox_path: Optional[str] = None,
        archive_name: Optional[str] = None,
        output_subdir: Optional[str] = DEFAULT_BUNDLE_SUBDIR,
        include_linked_files: bool = True,
        missing_reference_policy: str = "error",
        overwrite: bool = False,
        operation: str = "package",
        distribution_scope: str = "workspace",
        recipient_ref: Optional[str] = None,
        provenance_manifest: Any = None,
        disclosure_review: Any = None,
    ) -> Dict[str, Any]:
        return await self._execute(
            governance_context=None,
            report_path=report_path,
            workspace_id=workspace_id,
            sandbox_path=sandbox_path,
            archive_name=archive_name,
            output_subdir=output_subdir,
            include_linked_files=include_linked_files,
            missing_reference_policy=missing_reference_policy,
            overwrite=overwrite,
            operation=operation,
            distribution_scope=distribution_scope,
            recipient_ref=recipient_ref,
            provenance_manifest=provenance_manifest,
            disclosure_review=disclosure_review,
        )

    async def execute_with_context(
        self,
        *,
        governance_context: VerifiedToolExecutionContext | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        return await self._execute(
            governance_context=governance_context,
            **kwargs,
        )

    async def _execute(
        self,
        *,
        governance_context: VerifiedToolExecutionContext | None,
        report_path: str,
        workspace_id: Optional[str] = None,
        sandbox_path: Optional[str] = None,
        archive_name: Optional[str] = None,
        output_subdir: Optional[str] = DEFAULT_BUNDLE_SUBDIR,
        include_linked_files: bool = True,
        missing_reference_policy: str = "error",
        overwrite: bool = False,
        operation: str = "package",
        distribution_scope: str = "workspace",
        recipient_ref: Optional[str] = None,
        provenance_manifest: Any = None,
        disclosure_review: Any = None,
    ) -> Dict[str, Any]:
        """Analyze or package through the single disclosure decision path."""
        if governance_context is None:
            raise ValueError("verified_tool_execution_context_required")
        safe_workspace_id, sandbox_root = resolve_workspace_sandbox(
            workspace_id=workspace_id or governance_context.workspace_id,
            sandbox_path=sandbox_path,
        )
        safe_report_path = _validate_report_path(report_path)
        source_lexical = sandbox_root.joinpath(*safe_report_path.parts)
        if contains_symlink(source_lexical, sandbox_root):
            raise ValueError("report_path must not use symlinks")
        source_path = resolve_sandbox_relative_path(
            sandbox_root,
            safe_report_path,
            field_name="report_path",
        )
        safe_archive_name = _validate_archive_name(
            archive_name,
            safe_report_path,
        )
        safe_output_subdir = validate_relative_path(
            output_subdir,
            field_name="output_subdir",
            default=DEFAULT_BUNDLE_SUBDIR,
        )
        policy = _validate_missing_reference_policy(
            missing_reference_policy,
        )
        normalized_operation = (operation or "package").strip().lower()
        if normalized_operation not in OPERATIONS:
            raise ValueError("operation must be package or preflight")
        normalized_scope = (
            distribution_scope or "workspace"
        ).strip().lower()
        if normalized_scope not in DISTRIBUTION_SCOPES:
            raise ValueError(
                "distribution_scope must be workspace, "
                "workspace_group, or external"
            )
        if normalized_scope == "external" and (
            not isinstance(recipient_ref, str)
            or not recipient_ref.strip()
        ):
            raise ValueError("recipient_ref is required for external scope")
        if governance_context.workspace_id != safe_workspace_id:
            raise ValueError("governance_context_workspace_mismatch")
        graph = collect_report_bundle_graph(
            sandbox_root=sandbox_root,
            report_path=source_path,
            include_linked_files=bool(include_linked_files),
        )
        if graph.missing_references and policy == "error":
            first = graph.missing_references[0]
            graph.close()
            raise ValueError(
                "report bundle has missing local references: "
                f"{first.source} -> {first.reference}"
            )

        target_dir_lexical = sandbox_root.joinpath(*safe_output_subdir.parts)
        if contains_symlink(target_dir_lexical, sandbox_root):
            raise ValueError("output_subdir must not use symlinks")
        target_dir = target_dir_lexical.resolve()
        target_path = (target_dir / safe_archive_name).resolve()
        if not is_relative_to(target_path, sandbox_root):
            raise ValueError("report bundle target must remain under sandbox root")
        if target_path == source_path:
            raise ValueError("report bundle target must differ from report_path")

        disclosure_plan = self._disclosure_adapter.evaluate(
            graph=graph,
            governance_context=governance_context,
            distribution_scope=normalized_scope,
            recipient_ref=recipient_ref,
            provenance_manifest=provenance_manifest,
            disclosure_review=disclosure_review,
        )
        decision = disclosure_plan.decision
        common_result = {
            "success": True,
            "terminal": True,
            "artifact_kind": "report_share_bundle",
            "workspace_id": safe_workspace_id,
            "distribution_scope": normalized_scope,
            "share_authorization": decision.share_authorization,
            "artifact_set_sha256": decision.artifact_set_sha256,
            "graph_sha256": decision.artifact_set_sha256,
            "policy_version": decision.policy.version,
            "policy_sha256": decision.policy.content_sha256,
            "decision_sha256": decision.decision_sha256,
            "scope_evidence_sha256": decision.scope_evidence_sha256,
            "review_binding_sha256": decision.review_binding_sha256,
            "review_receipt_sha256": decision.review_receipt_sha256,
            "review_requirements": list(decision.review_requirements),
            "blocking_codes": list(decision.blocking_codes),
            "source_report_sha256": graph.source_report_sha256,
            "file_count": len(graph.files),
            "total_uncompressed_bytes": graph.total_uncompressed_bytes,
            "max_files": MAX_BUNDLE_FILES,
            "max_uncompressed_bytes": MAX_BUNDLE_SOURCE_BYTES,
        }
        if normalized_operation == "preflight":
            result = {
                **common_result,
                "status": "preflight_completed",
                "artifact_created": False,
            }
            graph.close()
            return result
        if not disclosure_plan.can_package:
            code = (
                decision.blocking_codes[0]
                if decision.blocking_codes
                else "disclosure_review_required"
            )
            graph.close()
            raise ValueError(f"report_disclosure_blocked:{code}")

        archive_result = write_report_bundle_archive(
            plan=disclosure_plan,
            target_path=target_path,
            overwrite=bool(overwrite),
        )
        manifest = archive_result["manifest"]
        bundle_completeness = manifest["bundle_status"]

        result = {
            **common_result,
            "status": "completed",
            "artifact_created": True,
            "archive_format": "zip",
            "content_type": "application/zip",
            "workspace_id": safe_workspace_id,
            "sandbox_path": str(sandbox_root),
            "relative_path": str(
                PurePosixPath(*safe_output_subdir.parts)
                / safe_archive_name
            ),
            "archive_path": str(target_path),
            "entrypoint": "index.html",
            "bundle_completeness": bundle_completeness,
            "archive_sha256": archive_result["archive_sha256"],
            "archive_size": archive_result["archive_size"],
            "missing_references": manifest["missing_references"],
            "external_references": manifest["external_references"],
            "manifest": manifest,
            "file_existed": archive_result["file_existed"],
            "overwrite": bool(overwrite),
        }
        graph.close()
        return result


__all__ = [
    "DEFAULT_BUNDLE_SUBDIR",
    "MISSING_REFERENCE_POLICIES",
    "OPERATIONS",
    "DISTRIBUTION_SCOPES",
    "WorkspaceReportBundleTool",
]
