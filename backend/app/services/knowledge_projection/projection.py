"""Deterministic knowledge views; Markdown is a rebuildable artifact, never truth."""

import hashlib
import json
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text

from backend.app.services.knowledge_projection.contracts import (
    KnowledgeProjectionRequest,
    KnowledgeProjectionResult,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase


class KnowledgeProjectionConflictError(RuntimeError):
    pass


class KnowledgeProjectionRepository(PostgresStoreBase):
    def get_or_create_manifest(
        self,
        *,
        projection_id: str,
        request: KnowledgeProjectionRequest,
        input_revision_hash: str,
        content_hash: str,
        evidence_refs: list[str],
    ) -> Tuple[Dict[str, Any], bool]:
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    WITH inserted AS (
                        INSERT INTO knowledge_projection_manifests (
                            id, projection_type, scope_type, scope_id,
                            topology_snapshot_id, input_revision_hash,
                            content_hash, artifact_ref, generator_revision,
                            evidence_refs, metadata, generated_at
                        ) VALUES (
                            :id, :projection_type, :scope_type, :scope_id,
                            :topology_snapshot_id, :input_revision_hash,
                            :content_hash, :artifact_ref, :generator_revision,
                            CAST(:evidence_refs AS jsonb), CAST(:metadata AS jsonb),
                            :generated_at
                        )
                        ON CONFLICT (
                            projection_type, scope_type, scope_id,
                            input_revision_hash
                        ) DO NOTHING
                        RETURNING *, TRUE AS created
                    )
                    SELECT * FROM inserted
                    UNION ALL
                    SELECT manifest.*, FALSE AS created
                    FROM knowledge_projection_manifests AS manifest
                    WHERE projection_type = :projection_type
                      AND scope_type = :scope_type
                      AND scope_id = :scope_id
                      AND input_revision_hash = :input_revision_hash
                    LIMIT 1
                    """
                ),
                {
                    "id": projection_id,
                    "projection_type": request.projection_type,
                    "scope_type": request.scope_type,
                    "scope_id": request.scope_id,
                    "topology_snapshot_id": request.topology_snapshot_id,
                    "input_revision_hash": input_revision_hash,
                    "content_hash": content_hash,
                    "artifact_ref": request.artifact_ref,
                    "generator_revision": request.generator_revision,
                    "evidence_refs": self.serialize_json(evidence_refs),
                    "metadata": self.serialize_json(request.metadata),
                    "generated_at": request.logical_generated_at,
                },
            ).fetchone()
        if row is None:
            raise RuntimeError("knowledge projection manifest admission failed")
        data = dict(row._mapping if hasattr(row, "_mapping") else row)
        return data, bool(data.pop("created"))


class KnowledgeProjectionService:
    def __init__(
        self,
        repository: Optional[KnowledgeProjectionRepository] = None,
    ) -> None:
        self.repository = repository or KnowledgeProjectionRepository()

    def project(self, request: KnowledgeProjectionRequest) -> KnowledgeProjectionResult:
        canonical, input_revision_hash, evidence_refs = self._canonicalize(request)
        projection_id = "kp_" + hashlib.sha256(
            (
                f"{request.projection_type}\0{request.scope_type}\0"
                f"{request.scope_id}\0{input_revision_hash}"
            ).encode("utf-8")
        ).hexdigest()[:32]
        markdown = self._render_markdown(
            request,
            projection_id=projection_id,
            input_revision_hash=input_revision_hash,
            canonical_entries=canonical["entries"],
            evidence_refs=evidence_refs,
        )
        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        manifest, created = self.repository.get_or_create_manifest(
            projection_id=projection_id,
            request=request,
            input_revision_hash=input_revision_hash,
            content_hash=content_hash,
            evidence_refs=evidence_refs,
        )
        if manifest["content_hash"] != content_hash:
            raise KnowledgeProjectionConflictError(
                "same projection revision produced a different content hash"
            )
        return KnowledgeProjectionResult(
            projection_id=manifest["id"],
            input_revision_hash=input_revision_hash,
            content_hash=content_hash,
            markdown=markdown,
            artifact_ref=manifest["artifact_ref"],
            created=created,
        )

    @staticmethod
    def _canonicalize(
        request: KnowledgeProjectionRequest,
    ) -> Tuple[Dict[str, Any], str, list[str]]:
        entries = sorted(
            (
                entry.model_dump(mode="json")
                for entry in request.entries
            ),
            key=lambda entry: (
                entry["stable_subject_key"],
                entry["memory_version_id"],
            ),
        )
        for entry in entries:
            entry["evidence_refs"] = sorted(set(entry["evidence_refs"]))
        evidence_refs = sorted(
            {
                evidence_ref
                for entry in entries
                for evidence_ref in entry["evidence_refs"]
            }
        )
        canonical = {
            "projection_type": request.projection_type,
            "scope_type": request.scope_type,
            "scope_id": request.scope_id,
            "topology_snapshot_id": request.topology_snapshot_id,
            "policy_revision": request.policy_revision,
            "entries": entries,
        }
        encoded = json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return (
            canonical,
            hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            evidence_refs,
        )

    @staticmethod
    def _render_markdown(
        request: KnowledgeProjectionRequest,
        *,
        projection_id: str,
        input_revision_hash: str,
        canonical_entries: list[Dict[str, Any]],
        evidence_refs: list[str],
    ) -> str:
        frontmatter = {
            "projection_id": projection_id,
            "projection_type": request.projection_type,
            "scope": f"{request.scope_type}:{request.scope_id}",
            "topology_snapshot_id": request.topology_snapshot_id,
            "input_revision_hash": input_revision_hash,
            "generated_at": request.logical_generated_at.isoformat(),
            "generator_revision": request.generator_revision,
            "evidence_index": evidence_refs,
        }
        lines = ["---"]
        for key, value in frontmatter.items():
            lines.append(
                f"{key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
            )
        lines.extend(["---", "", f"# {request.projection_type}", ""])
        for entry in canonical_entries:
            heading = entry["title"] or entry["stable_subject_key"]
            lines.extend(
                [
                    f"## {heading}",
                    "",
                    entry["claim"],
                    "",
                    (
                        f"Status: {entry['lifecycle_status']} / "
                        f"{entry['verification_status']} · "
                        f"confidence={entry['confidence']:.3f}"
                    ),
                ]
            )
            if entry["summary"]:
                lines.extend(["", entry["summary"]])
            if entry["evidence_refs"]:
                lines.extend(
                    [
                        "",
                        "Evidence: "
                        + ", ".join(entry["evidence_refs"]),
                    ]
                )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
