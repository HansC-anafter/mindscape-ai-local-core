"""Atomic PostgreSQL writer for group synthesis candidates and conflicts."""

import hashlib
import json
from itertools import combinations
from typing import Any, Dict, Sequence

from sqlalchemy import bindparam, text

from backend.app.services.knowledge_projection.contracts import (
    GroupSynthesisHandoff,
    GroupSynthesisReceipt,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase


class GroupSynthesisBoundaryError(PermissionError):
    pass


class GroupSynthesisRepository(PostgresStoreBase):
    """One short transaction owns all durable group candidate writes."""

    def commit(
        self,
        handoff: GroupSynthesisHandoff,
        plan: Dict[str, Any],
    ) -> GroupSynthesisReceipt:
        with self.transaction() as conn:
            snapshot = conn.execute(
                text(
                    """
                    SELECT group_id FROM workspace_group_topology_snapshots
                    WHERE id = :snapshot_id
                    """
                ),
                {"snapshot_id": handoff.topology_snapshot_id},
            ).fetchone()
            if snapshot is None or snapshot.group_id != handoff.group_id:
                raise GroupSynthesisBoundaryError(
                    "handoff group does not match its topology snapshot"
                )

            self._ensure_review_projection(conn, handoff, plan)
            inserted = conn.execute(
                text(
                    """
                    INSERT INTO group_synthesis_receipts (
                        id, run_id, group_id, topology_snapshot_id, input_hash,
                        policy_revision, status, candidate_memory_ids,
                        conflict_sets, review_projection_id, metadata
                    ) VALUES (
                        :id, :run_id, :group_id, :topology_snapshot_id,
                        :input_hash, :policy_revision, 'candidate',
                        CAST(:candidate_memory_ids AS jsonb),
                        CAST(:conflict_sets AS jsonb), :review_projection_id,
                        CAST(:metadata AS jsonb)
                    )
                    ON CONFLICT (run_id, input_hash) DO NOTHING
                    RETURNING *
                    """
                ),
                {
                    "id": plan["receipt_id"],
                    "run_id": handoff.run_id,
                    "group_id": handoff.group_id,
                    "topology_snapshot_id": handoff.topology_snapshot_id,
                    "input_hash": plan["input_hash"],
                    "policy_revision": handoff.policy_revision,
                    "candidate_memory_ids": self.serialize_json(
                        plan["candidate_memory_ids"]
                    ),
                    "conflict_sets": self.serialize_json(plan["conflict_sets"]),
                    "review_projection_id": plan["projection_id"],
                    "metadata": self.serialize_json(
                        {"claim_count": len(handoff.claims), "writer": "single"}
                    ),
                },
            ).fetchone()
            if inserted is None:
                existing = conn.execute(
                    text(
                        """
                        SELECT * FROM group_synthesis_receipts
                        WHERE run_id = :run_id AND input_hash = :input_hash
                        """
                    ),
                    {"run_id": handoff.run_id, "input_hash": plan["input_hash"]},
                ).fetchone()
                if existing is None:
                    raise RuntimeError("group synthesis conflict lookup failed")
                return self._row_to_receipt(existing, created=False)

            self._write_candidates(conn, handoff, plan)
            return self._row_to_receipt(inserted, created=True)

    def _ensure_review_projection(self, conn, handoff, plan) -> None:
        conn.execute(
            text(
                """
                INSERT INTO knowledge_projection_manifests (
                    id, projection_type, scope_type, scope_id,
                    topology_snapshot_id, input_revision_hash, content_hash,
                    artifact_ref, generator_revision, evidence_refs, metadata
                ) VALUES (
                    :id, 'human_review', 'human_review', :scope_id,
                    :snapshot_id, :input_hash, :content_hash, :artifact_ref,
                    :generator_revision, CAST(:evidence_refs AS jsonb),
                    CAST(:metadata AS jsonb)
                )
                ON CONFLICT (
                    projection_type, scope_type, scope_id, input_revision_hash
                ) DO NOTHING
                """
            ),
            {
                "id": plan["projection_id"],
                "scope_id": handoff.group_id,
                "snapshot_id": handoff.topology_snapshot_id,
                "input_hash": plan["input_hash"],
                "content_hash": plan["projection_content_hash"],
                "artifact_ref": f"projection://{plan['projection_id']}.md",
                "generator_revision": handoff.policy_revision,
                "evidence_refs": self.serialize_json(plan["evidence_refs"]),
                "metadata": self.serialize_json(
                    {"rebuildable": True, "canonical": False}
                ),
            },
        )

    def _write_candidates(self, conn, handoff, plan) -> None:
        rows = plan["candidate_rows"]
        if not rows:
            return
        conn.execute(
            text(
                """
                INSERT INTO memory_items (
                    id, kind, layer, scope, subject_type, subject_id,
                    context_type, context_id, title, claim, summary,
                    salience, confidence, verification_status,
                    lifecycle_status, update_mode, created_by_pipeline,
                    created_from_run_id, metadata
                ) VALUES (
                    :id, 'pattern_candidate', 'core', 'group',
                    'knowledge_subject', :subject_id, 'group', :group_id,
                    :title, :claim, :summary, 0.7, :confidence,
                    'unverified', 'candidate', 'merge',
                    'group_synthesis_v1', :run_id, CAST(:metadata AS jsonb)
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            [
                {
                    "id": row["memory_id"],
                    "subject_id": row["stable_subject_key"],
                    "group_id": handoff.group_id,
                    "title": row["title"] or row["stable_subject_key"],
                    "claim": row["claim"],
                    "summary": row["summary"],
                    "confidence": row["confidence"],
                    "run_id": handoff.run_id,
                    "metadata": self.serialize_json(
                        {
                            "stable_subject_key": row["stable_subject_key"],
                            "agent_ids": row["agent_ids"],
                            "agent_roles": row["agent_roles"],
                            "topology_snapshot_id": handoff.topology_snapshot_id,
                            "policy_revision": handoff.policy_revision,
                        }
                    ),
                }
                for row in rows
            ],
        )
        version_numbers = self._next_version_numbers(
            conn, plan["candidate_memory_ids"]
        )
        conn.execute(
            text(
                """
                INSERT INTO memory_versions (
                    id, memory_item_id, version_no, update_mode,
                    claim_snapshot, summary_snapshot, metadata_snapshot,
                    created_from_run_id
                ) VALUES (
                    :id, :memory_item_id, :version_no, 'merge',
                    :claim, :summary, CAST(:metadata AS jsonb), :run_id
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            [
                {
                    "id": "gmv_" + hashlib.sha256(
                        f"{handoff.run_id}\0{row['memory_id']}".encode("utf-8")
                    ).hexdigest()[:32],
                    "memory_item_id": row["memory_id"],
                    "version_no": version_numbers[row["memory_id"]],
                    "claim": row["claim"],
                    "summary": row["summary"],
                    "metadata": self.serialize_json(
                        {
                            "stable_subject_key": row["stable_subject_key"],
                            "evidence_refs": row["evidence_refs"],
                        }
                    ),
                    "run_id": handoff.run_id,
                }
                for row in rows
            ],
        )
        evidence_rows = [
            {
                "id": "gme_" + hashlib.sha256(
                    f"{row['memory_id']}\0{evidence_ref}".encode("utf-8")
                ).hexdigest()[:32],
                "memory_item_id": row["memory_id"],
                "evidence_id": evidence_ref,
                "confidence": row["confidence"],
                "metadata": self.serialize_json(
                    {
                        "agent_ids": row["agent_ids"],
                        "topology_snapshot_id": handoff.topology_snapshot_id,
                    }
                ),
            }
            for row in rows
            for evidence_ref in row["evidence_refs"]
        ]
        if evidence_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO memory_evidence_links (
                        id, memory_item_id, evidence_type, evidence_id,
                        link_role, confidence, metadata
                    ) VALUES (
                        :id, :memory_item_id, 'agent_output', :evidence_id,
                        'supports', :confidence, CAST(:metadata AS jsonb)
                    )
                    ON CONFLICT (
                        memory_item_id, evidence_type, evidence_id, link_role
                    ) DO NOTHING
                    """
                ),
                evidence_rows,
            )
        edge_rows = []
        for conflict in plan["conflict_sets"]:
            for left, right in combinations(conflict["memory_ids"], 2):
                edge_rows.extend(
                    [
                        self._edge_row(left, right, handoff.run_id),
                        self._edge_row(right, left, handoff.run_id),
                    ]
                )
        if edge_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO memory_edges (
                        id, from_memory_id, to_memory_id, edge_type,
                        evidence_strength, metadata
                    ) VALUES (
                        :id, :from_memory_id, :to_memory_id, 'contradicts',
                        1.0, CAST(:metadata AS jsonb)
                    )
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                edge_rows,
            )

    @staticmethod
    def _edge_row(left: str, right: str, run_id: str) -> Dict[str, str]:
        return {
            "id": "gmedge_" + hashlib.sha256(
                f"{left}\0{right}".encode("utf-8")
            ).hexdigest()[:30],
            "from_memory_id": left,
            "to_memory_id": right,
            "metadata": json.dumps({"run_id": run_id}, sort_keys=True),
        }

    @staticmethod
    def _next_version_numbers(conn, memory_ids: Sequence[str]) -> Dict[str, int]:
        query = text(
            """
            SELECT memory_item_id, COALESCE(MAX(version_no), 0) AS max_version
            FROM memory_versions
            WHERE memory_item_id IN :memory_ids
            GROUP BY memory_item_id
            """
        ).bindparams(bindparam("memory_ids", expanding=True))
        rows = conn.execute(query, {"memory_ids": list(memory_ids)}).fetchall()
        maxima = {row.memory_item_id: int(row.max_version) for row in rows}
        return {memory_id: maxima.get(memory_id, 0) + 1 for memory_id in memory_ids}

    def _row_to_receipt(self, row, *, created: bool) -> GroupSynthesisReceipt:
        return GroupSynthesisReceipt(
            receipt_id=row.id,
            run_id=row.run_id,
            group_id=row.group_id,
            topology_snapshot_id=row.topology_snapshot_id,
            input_hash=row.input_hash,
            status=row.status,
            candidate_memory_ids=self.deserialize_json(
                row.candidate_memory_ids, default=[]
            ),
            conflict_sets=self.deserialize_json(row.conflict_sets, default=[]),
            review_projection_id=row.review_projection_id,
            created=created,
        )
