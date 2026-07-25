"""Pure v1 reducer for compact workflow projections."""

from __future__ import annotations

from copy import deepcopy

from .canonical_json import sha256_hex


def reduce_v1(state: dict, event: dict) -> dict:
    updated = deepcopy(state)
    payload = event["payload"]
    if event["event_type"] == "transition":
        updated["current_state"] = payload.get("to_state", updated["current_state"])
        if (
            payload.get("to_state") == "promoted"
            and payload.get("release_workflow_id")
        ):
            updated["promotion_link"] = {
                "approval_consumption_id": payload[
                    "approval_consumption_id"
                ],
                "release_effect_receipt_id": payload[
                    "release_effect_receipt_id"
                ],
                "release_workflow_id": payload["release_workflow_id"],
            }
        typed = payload.get("typed_receipt") or {}
        if typed.get("receipt_type") == "product_iteration":
            updated["definition"] = deepcopy(typed["receipt"])
        elif typed.get("receipt_type") == "evaluation_receipt":
            updated["evaluation"] = deepcopy(typed["receipt"])
    elif event["event_type"] == "cancellation_requested":
        updated["cancellation_state"] = "requested"
    elif event["event_type"] == "product_iteration_defined":
        definition = deepcopy(payload["definition"])
        updated["definition"] = definition
        updated["evidence_frontier"] = deepcopy(
            definition["evidence_frontier"]
        )
        updated["enrollment_ids"] = []
        updated["accepted_observation_ids"] = []
        updated["accepted_observation_count"] = 0
        updated["adapter_refs_by_arm"] = {}
        updated["evaluation_attempt_count"] = 0
    elif event["event_type"] == "iteration_enrollment_accepted":
        enrollment = payload["enrollment"]
        enrollment_id = enrollment["enrollment_id"]
        updated.setdefault("enrollment_ids", []).append(enrollment_id)
        updated.setdefault("adapter_refs_by_arm", {})[
            enrollment["arm_id"]
        ] = {
            "capability_identity": deepcopy(
                enrollment["capability_identity"]
            ),
            "adapter_contract_version": enrollment[
                "adapter_contract_version"
            ],
            "descriptor_sha256": enrollment["descriptor_sha256"],
            "evaluator_version": enrollment["evaluator_version"],
            "review_lens": deepcopy(enrollment.get("review_lens")),
        }
    elif event["event_type"] == "outcome_observation_accepted":
        observation = payload["observation"]
        updated.setdefault("accepted_observation_ids", []).append(
            observation["observation_id"]
        )
        updated["accepted_observation_count"] = len(
            updated["accepted_observation_ids"]
        )
        frontier = updated.setdefault(
            "evidence_frontier",
            {
                "last_observation_sequence": 0,
                "frontier_hash": "0" * 64,
            },
        )
        frontier["last_observation_sequence"] = event["sequence"]
        frontier["frontier_hash"] = sha256_hex(
            {
                "previous_frontier_hash": frontier["frontier_hash"],
                "observation_id": observation["observation_id"],
                "provenance_hash": observation["provenance_hash"],
                "sequence": event["sequence"],
            }
        )
    elif event["event_type"] == "product_release_linked":
        updated["release_link"] = deepcopy(payload)
    typed = payload.get("typed_receipt") or {}
    if typed.get("receipt_type") == "evaluation_receipt":
        updated["evaluation_attempt_count"] = (
            int(updated.get("evaluation_attempt_count", 0)) + 1
        )
    elif typed.get("receipt_type") == "release_health_receipt":
        receipt = typed["receipt"]
        updated["release_health"] = {
            "receipt_id": receipt["receipt_id"],
            "release_id": receipt["release_id"],
            "candidate_attestation_id": receipt[
                "candidate_attestation_id"
            ],
            "window": deepcopy(receipt["window"]),
            "slo": deepcopy(receipt["slo"]),
            "error_budget": deepcopy(receipt["error_budget"]),
            "quality": deepcopy(receipt["quality"]),
            "safety": deepcopy(receipt["safety"]),
            "resource": deepcopy(receipt["resource"]),
            "drift": deepcopy(receipt["drift"]),
            "incident_refs": deepcopy(receipt["incident_refs"]),
            "decision": receipt["decision"],
            "recorded_at": receipt["recorded_at"],
        }
    elif typed.get("receipt_type") == "evidence_lifecycle_manifest":
        receipt = typed["receipt"]
        updated["evidence_lifecycle"] = {
            "manifest_id": receipt["manifest_id"],
            "evidence_class": receipt["evidence_class"],
            "content_hash": receipt["content_hash"],
            "object_ref": deepcopy(receipt["object_ref"]),
            "privacy_classification": receipt[
                "privacy_classification"
            ],
            "legal_hold": receipt["legal_hold"],
            "lifecycle_action": receipt["lifecycle_action"],
            "reconciliation_state": receipt[
                "reconciliation_state"
            ],
        }
    updated["last_sequence"] = event["sequence"]
    updated["last_event_hash"] = event["event_hash"]
    return updated
