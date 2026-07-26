"""Create deterministic ZIP archives from workspace report dependency graphs."""

from __future__ import annotations

import hashlib
import html
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from backend.app.services.tools.reporting.report_disclosure_adapter import (
    ReportBundleDisclosureFile,
    ReportBundleDisclosurePlan,
)


REPORT_BUNDLE_SCHEMA_VERSION = "mindscape.report-share-bundle.v2"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_ZIP_FILE_MODE = 0o100644 << 16


def build_report_bundle_manifest(
    plan: ReportBundleDisclosurePlan,
) -> dict[str, Any]:
    """Build the stable manifest included in every report bundle."""
    graph = plan.graph
    files = [
        {
            "source_path": item.source_file.sandbox_relative_path,
            "archive_path": item.archive_path,
            "size": item.output_size,
            "sha256": item.output_sha256,
            "source_size": item.source_file.size,
            "source_sha256": item.source_file.sha256,
            "output_sha256": item.output_sha256,
            "classification": item.classification,
            "action": item.action,
            "findings": [
                {"code": code, "count": count}
                for code, count in item.finding_counts
            ],
        }
        for item in plan.files
    ]
    return {
        "schema_version": REPORT_BUNDLE_SCHEMA_VERSION,
        "bundle_status": (
            "partial" if graph.missing_references else "complete"
        ),
        "entrypoint": graph.entrypoint,
        "source_report": graph.report_path.name,
        "source_report_path": next(
            source_file.sandbox_relative_path
            for source_file in graph.files
            if source_file.path == graph.report_path
        ),
        "source_root": graph.source_root_relative,
        "source_report_sha256": graph.source_report_sha256,
        "graph_sha256": plan.decision.artifact_set_sha256,
        "file_count": len(graph.files),
        "total_uncompressed_bytes": graph.total_uncompressed_bytes,
        "distribution_scope": plan.decision.target_scope,
        "share_authorization": plan.decision.share_authorization,
        "policy_version": plan.decision.policy.version,
        "policy_sha256": plan.decision.policy.content_sha256,
        "decision_sha256": plan.decision.decision_sha256,
        "scope_evidence_sha256": (
            plan.decision.scope_evidence_sha256
        ),
        "review_binding_sha256": (
            plan.decision.review_binding_sha256
        ),
        "review_receipt_sha256": (
            plan.decision.review_receipt_sha256
        ),
        "missing_references": [
            entry.to_dict() for entry in graph.missing_references
        ],
        "external_references": [
            entry.to_dict() for entry in graph.external_references
        ],
        "files": files,
    }


def _zip_info(archive_path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(archive_path, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = _ZIP_FILE_MODE
    info.create_system = 3
    return info


def _write_bytes(
    archive: zipfile.ZipFile,
    archive_path: str,
    content: bytes,
) -> None:
    archive.writestr(
        _zip_info(archive_path),
        content,
        compress_type=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    )


def _write_source_file(
    archive: zipfile.ZipFile,
    item: ReportBundleDisclosureFile,
) -> None:
    if (
        item.transformed_content is not None
        or item.transformed_content_file is not None
    ):
        _verify_source_file(item)
    if item.transformed_content is not None:
        if (
            hashlib.sha256(item.transformed_content).hexdigest()
            != item.output_sha256
        ):
            raise ValueError("artifact_transformed_hash_drift")
        _write_bytes(
            archive,
            item.archive_path,
            item.transformed_content,
        )
        return
    if item.transformed_content_file is not None:
        digest = hashlib.sha256()
        output_bytes = 0
        source = item.transformed_content_file
        source.seek(0)
        with archive.open(
            _zip_info(item.archive_path),
            mode="w",
            force_zip64=True,
        ) as destination:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                output_bytes += len(chunk)
                destination.write(chunk)
        source.seek(0)
        if output_bytes != item.output_size:
            raise ValueError("artifact_transformed_size_drift")
        if digest.hexdigest() != item.output_sha256:
            raise ValueError("artifact_transformed_hash_drift")
        return
    digest = hashlib.sha256()
    source_bytes = 0
    with item.source_file.path.open("rb") as source:
        with archive.open(
            _zip_info(item.archive_path),
            mode="w",
            force_zip64=True,
        ) as destination:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                source_bytes += len(chunk)
                destination.write(chunk)
    if source_bytes != item.source_file.size:
        raise ValueError("artifact_source_size_drift")
    if digest.hexdigest() != item.source_file.sha256:
        raise ValueError("artifact_source_hash_drift")


def _verify_source_file(item: ReportBundleDisclosureFile) -> None:
    digest = hashlib.sha256()
    source_bytes = 0
    with item.source_file.path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            source_bytes += len(chunk)
    if source_bytes != item.source_file.size:
        raise ValueError("artifact_source_size_drift")
    if digest.hexdigest() != item.source_file.sha256:
        raise ValueError("artifact_source_hash_drift")


def _build_index_html(entrypoint: str) -> bytes:
    target = quote(entrypoint, safe="/._-")
    escaped_target = html.escape(target, quote=True)
    document = (
        "<!doctype html>\n"
        '<html lang="zh-TW">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'  <meta http-equiv="refresh" content="0; url={escaped_target}">\n'
        "  <title>Open report</title>\n"
        "</head>\n"
        "<body>\n"
        f'  <p><a href="{escaped_target}">Open report</a></p>\n'
        "</body>\n"
        "</html>\n"
    )
    return document.encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_report_bundle_archive(
    *,
    plan: ReportBundleDisclosurePlan,
    target_path: Path,
    overwrite: bool,
) -> dict[str, Any]:
    """Atomically write a deterministic report bundle ZIP."""
    if not plan.can_package:
        raise ValueError("report_disclosure_plan_not_authorized")
    graph = plan.graph
    target_path.parent.mkdir(parents=True, exist_ok=True)
    file_existed = target_path.exists()
    if file_existed and not overwrite:
        raise ValueError("report bundle already exists and overwrite is false")

    manifest = build_report_bundle_manifest(plan)
    manifest_bytes = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)

        with zipfile.ZipFile(
            temp_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
        ) as archive:
            _write_bytes(archive, "index.html", _build_index_html(graph.entrypoint))
            _write_bytes(archive, "manifest.json", manifest_bytes)
            for item in plan.files:
                _write_source_file(archive, item)

        if overwrite:
            os.replace(temp_path, target_path)
        else:
            try:
                os.link(temp_path, target_path)
            except FileExistsError as exc:
                raise ValueError(
                    "report bundle already exists and overwrite is false"
                ) from exc
            temp_path.unlink()
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return {
        "manifest": manifest,
        "archive_sha256": _sha256_file(target_path),
        "archive_size": target_path.stat().st_size,
        "file_existed": file_existed,
    }


__all__ = [
    "REPORT_BUNDLE_SCHEMA_VERSION",
    "build_report_bundle_manifest",
    "write_report_bundle_archive",
]
