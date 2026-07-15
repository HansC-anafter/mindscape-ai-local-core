"""Multi-reader/single-writer group synthesis and explicit human review."""

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import bindparam, text

from backend.app.services.knowledge_projection.contracts import (
    GroupSynthesisHandoff,
    GroupSynthesisReceipt,
    GroupSynthesisReviewCommand,
    GroupSynthesisReviewReceipt,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.services.workspace_groups.facade import WorkspaceGroupFacade


from backend.app.services.knowledge_projection.synthesis_repository import (
    GroupSynthesisBoundaryError,
    GroupSynthesisRepository,
)


class GroupSynthesisStateError(RuntimeError):
    pass


class GroupSynthesisPlanner:
    """Canonicalize claims without using agent order or completion time as truth."""

    @staticmethod
    def plan(handoff: GroupSynthesisHandoff) -> Dict[str, Any]:
        canonical_claims = sorted(
            (claim.model_dump(mode="json") for claim in handoff.claims),
            key=lambda claim: (
                claim["stable_subject_key"],
                _normalize_claim(claim["claim"]),
                claim["agent_id"],
            ),
        )
        input_payload = {
            "run_id": handoff.run_id,
            "group_id": handoff.group_id,
            "topology_snapshot_id": handoff.topology_snapshot_id,
            "policy_revision": handoff.policy_revision,
            "claims": canonical_claims,
        }
        input_hash = _hash_json(input_payload)
        variants: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for claim in canonical_claims:
            normalized = _normalize_claim(claim["claim"])
            key = (claim["stable_subject_key"], normalized)
            variant = variants.setdefault(
                key,
                {
                    "stable_subject_key": claim["stable_subject_key"],
                    "normalized_claim": normalized,
                    "title": claim["title"],
                    "claim": claim["claim"].strip(),
                    "summary": claim["summary"].strip(),
                    "confidence": claim["confidence"],
                    "agent_ids": [],
                    "agent_roles": [],
                    "evidence_refs": [],
                },
            )
            variant["confidence"] = max(variant["confidence"], claim["confidence"])
            variant["agent_ids"].append(claim["agent_id"])
            variant["agent_roles"].append(claim["agent_role"])
            variant["evidence_refs"].extend(claim["evidence_refs"])

        candidate_rows = []
        by_subject: Dict[str, List[str]] = {}
        for key in sorted(variants):
            variant = variants[key]
            variant["agent_ids"] = sorted(set(variant["agent_ids"]))
            variant["agent_roles"] = sorted(set(variant["agent_roles"]))
            variant["evidence_refs"] = sorted(set(variant["evidence_refs"]))
            memory_id = "gmem_" + hashlib.sha256(
                (
                    f"{handoff.group_id}\0{variant['stable_subject_key']}\0"
                    f"{variant['normalized_claim']}"
                ).encode("utf-8")
            ).hexdigest()[:32]
            variant["memory_id"] = memory_id
            candidate_rows.append(variant)
            by_subject.setdefault(variant["stable_subject_key"], []).append(memory_id)

        conflict_sets = [
            {
                "stable_subject_key": subject,
                "memory_ids": sorted(memory_ids),
            }
            for subject, memory_ids in sorted(by_subject.items())
            if len(memory_ids) > 1
        ]
        receipt_id = "gsr_" + hashlib.sha256(
            f"{handoff.run_id}\0{input_hash}".encode("utf-8")
        ).hexdigest()[:32]
        projection_id = "kp_" + hashlib.sha256(
            f"human_review\0group\0{handoff.group_id}\0{input_hash}".encode("utf-8")
        ).hexdigest()[:32]
        review_markdown = _render_review_markdown(handoff, candidate_rows, conflict_sets)
        return {
            "input_hash": input_hash,
            "receipt_id": receipt_id,
            "projection_id": projection_id,
            "projection_content_hash": hashlib.sha256(
                review_markdown.encode("utf-8")
            ).hexdigest(),
            "candidate_rows": candidate_rows,
            "candidate_memory_ids": [row["memory_id"] for row in candidate_rows],
            "conflict_sets": conflict_sets,
            "evidence_refs": sorted(
                {
                    ref
                    for row in candidate_rows
                    for ref in row["evidence_refs"]
                }
            ),
            "review_markdown": review_markdown,
        }


class GroupSynthesisCommitter:
    def __init__(
        self,
        repository: Optional[GroupSynthesisRepository] = None,
    ) -> None:
        self.repository = repository or GroupSynthesisRepository()

    def commit(self, handoff: GroupSynthesisHandoff) -> GroupSynthesisReceipt:
        return self.repository.commit(handoff, GroupSynthesisPlanner.plan(handoff))


class GroupSynthesisReviewRepository(PostgresStoreBase):
    def decide(
        self,
        command: GroupSynthesisReviewCommand,
        *,
        review_id: str,
        decision_hash: str,
    ) -> GroupSynthesisReviewReceipt:
        with self.transaction() as conn:
            synthesis = conn.execute(
                text(
                    """
                    SELECT * FROM group_synthesis_receipts
                    WHERE id = :id FOR UPDATE
                    """
                ),
                {"id": command.synthesis_receipt_id},
            ).fetchone()
            if synthesis is None:
                raise GroupSynthesisStateError("synthesis receipt not found")
            target_status = {
                "approve": "approved",
                "request_changes": "changes_requested",
                "reject": "rejected",
            }[command.decision]
            if synthesis.status in {"approved", "rejected"}:
                existing = conn.execute(
                    text(
                        """
                        SELECT * FROM group_synthesis_review_receipts
                        WHERE synthesis_receipt_id = :receipt_id
                          AND decision_hash = :decision_hash
                        """
                    ),
                    {
                        "receipt_id": command.synthesis_receipt_id,
                        "decision_hash": decision_hash,
                    },
                ).fetchone()
                if existing is not None:
                    return self._row_to_review(existing, created=False)
                raise GroupSynthesisStateError(
                    f"synthesis is already terminal: {synthesis.status}"
                )
            inserted = conn.execute(
                text(
                    """
                    INSERT INTO group_synthesis_review_receipts (
                        id, synthesis_receipt_id, decision, actor_user_id,
                        reason, decision_hash
                    ) VALUES (
                        :id, :synthesis_receipt_id, :decision, :actor_user_id,
                        :reason, :decision_hash
                    )
                    ON CONFLICT (synthesis_receipt_id, decision_hash) DO NOTHING
                    RETURNING *
                    """
                ),
                {
                    "id": review_id,
                    **command.model_dump(),
                    "decision_hash": decision_hash,
                },
            ).fetchone()
            if inserted is None:
                existing = conn.execute(
                    text(
                        """
                        SELECT * FROM group_synthesis_review_receipts
                        WHERE synthesis_receipt_id = :receipt_id
                          AND decision_hash = :decision_hash
                        """
                    ),
                    {
                        "receipt_id": command.synthesis_receipt_id,
                        "decision_hash": decision_hash,
                    },
                ).fetchone()
                return self._row_to_review(existing, created=False)
            memory_ids = self.deserialize_json(
                synthesis.candidate_memory_ids, default=[]
            )
            if command.decision in {"approve", "reject"} and memory_ids:
                version_numbers = GroupSynthesisRepository._next_version_numbers(
                    conn, memory_ids
                )
                lifecycle = "active" if command.decision == "approve" else "archived"
                verification = (
                    "verified" if command.decision == "approve" else "rejected"
                )
                conn.execute(
                    text(
                        """
                        UPDATE memory_items
                        SET lifecycle_status = :lifecycle_status,
                            verification_status = :verification_status,
                            last_confirmed_at = CASE
                                WHEN :verification_status = 'verified' THEN NOW()
                                ELSE last_confirmed_at
                            END,
                            updated_at = NOW()
                        WHERE id IN :memory_ids
                          AND context_type = 'group'
                          AND context_id = :group_id
                        """
                    ).bindparams(bindparam("memory_ids", expanding=True)),
                    {
                        "lifecycle_status": lifecycle,
                        "verification_status": verification,
                        "memory_ids": memory_ids,
                        "group_id": synthesis.group_id,
                    },
                )
                item_rows = conn.execute(
                    text(
                        """
                        SELECT id, claim, summary, metadata
                        FROM memory_items WHERE id IN :memory_ids
                        """
                    ).bindparams(bindparam("memory_ids", expanding=True)),
                    {"memory_ids": memory_ids},
                ).fetchall()
                conn.execute(
                    text(
                        """
                        INSERT INTO memory_versions (
                            id, memory_item_id, version_no, update_mode,
                            claim_snapshot, summary_snapshot, metadata_snapshot,
                            created_from_run_id
                        ) VALUES (
                            :id, :memory_item_id, :version_no, 'append',
                            :claim, :summary, CAST(:metadata AS jsonb), :run_id
                        )
                        ON CONFLICT (id) DO NOTHING
                        """
                    ),
                    [
                        {
                            "id": "gmrv_" + hashlib.sha256(
                                f"{review_id}\0{row.id}".encode("utf-8")
                            ).hexdigest()[:31],
                            "memory_item_id": row.id,
                            "version_no": version_numbers[row.id],
                            "claim": row.claim,
                            "summary": row.summary,
                            "metadata": self.serialize_json(
                                {
                                    **self.deserialize_json(row.metadata, default={}),
                                    "group_review_receipt_id": review_id,
                                    "group_review_decision": command.decision,
                                }
                            ),
                            "run_id": review_id,
                        }
                        for row in item_rows
                    ],
                )
            conn.execute(
                text(
                    """
                    UPDATE group_synthesis_receipts
                    SET status = :status
                    WHERE id = :id
                    """
                ),
                {"status": target_status, "id": synthesis.id},
            )
            return self._row_to_review(inserted, created=True)

    @staticmethod
    def _row_to_review(row, *, created: bool) -> GroupSynthesisReviewReceipt:
        return GroupSynthesisReviewReceipt(
            id=row.id,
            synthesis_receipt_id=row.synthesis_receipt_id,
            decision=row.decision,
            actor_user_id=row.actor_user_id,
            reason=row.reason,
            decision_hash=row.decision_hash,
            created_at=row.created_at,
            created=created,
        )

    def group_id_for_receipt(self, receipt_id: str) -> str:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT group_id FROM group_synthesis_receipts WHERE id = :id
                    """
                ),
                {"id": receipt_id},
            ).fetchone()
        if row is None:
            raise GroupSynthesisStateError("synthesis receipt not found")
        return row.group_id


class GroupSynthesisReviewService:
    def __init__(
        self,
        *,
        repository: Optional[GroupSynthesisReviewRepository] = None,
        group_facade: Optional[WorkspaceGroupFacade] = None,
    ) -> None:
        self.repository = repository or GroupSynthesisReviewRepository()
        self.group_facade = group_facade or WorkspaceGroupFacade()

    def decide(
        self,
        command: GroupSynthesisReviewCommand,
        *,
        allowed_group_ids: Sequence[str] = (),
    ) -> GroupSynthesisReviewReceipt:
        group_id = self.repository.group_id_for_receipt(
            command.synthesis_receipt_id
        )
        self.group_facade.get_group(
            group_id,
            actor_user_id=command.actor_user_id,
            allowed_group_ids=allowed_group_ids,
        )
        payload = command.model_dump(mode="json")
        decision_hash = _hash_json(payload)
        review_id = "gsrr_" + hashlib.sha256(
            f"{command.synthesis_receipt_id}\0{decision_hash}".encode("utf-8")
        ).hexdigest()[:31]
        return self.repository.decide(
            command,
            review_id=review_id,
            decision_hash=decision_hash,
        )


def _normalize_claim(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _render_review_markdown(
    handoff: GroupSynthesisHandoff,
    candidate_rows: List[Dict[str, Any]],
    conflict_sets: List[Dict[str, Any]],
) -> str:
    lines = [
        "# Group knowledge review",
        "",
        f"Group: {handoff.group_id}",
        f"Snapshot: {handoff.topology_snapshot_id}",
        f"Run: {handoff.run_id}",
        "",
    ]
    conflict_ids = {
        memory_id
        for conflict in conflict_sets
        for memory_id in conflict["memory_ids"]
    }
    for row in candidate_rows:
        lines.extend(
            [
                f"## {row['title'] or row['stable_subject_key']}",
                "",
                row["claim"],
                "",
                f"Agents: {', '.join(row['agent_ids'])}",
                f"Roles: {', '.join(row['agent_roles'])}",
                f"Confidence: {row['confidence']:.3f}",
                f"Conflict: {'yes' if row['memory_id'] in conflict_ids else 'no'}",
                f"Evidence: {', '.join(row['evidence_refs']) or '(none)'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
