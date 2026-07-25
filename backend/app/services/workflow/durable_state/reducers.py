"""Pure v1 reducer for compact workflow projections."""

from __future__ import annotations

from copy import deepcopy

from .canonical_json import sha256_hex


def reduce_v1(state: dict, event: dict) -> dict:
    updated = deepcopy(state)
    payload = event["payload"]
    if event["event_type"] == "transition":
        updated["current_state"] = payload.get("to_state", updated["current_state"])
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
    elif event["event_type"] == "iteration_enrollment_accepted":
        enrollment_id = payload["enrollment"]["enrollment_id"]
        updated.setdefault("enrollment_ids", []).append(enrollment_id)
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
    updated["last_sequence"] = event["sequence"]
    updated["last_event_hash"] = event["event_hash"]
    return updated
