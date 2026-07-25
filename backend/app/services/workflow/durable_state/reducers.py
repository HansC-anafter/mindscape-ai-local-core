"""Pure v1 reducer for compact workflow projections."""

from __future__ import annotations

from copy import deepcopy


def reduce_v1(state: dict, event: dict) -> dict:
    updated = deepcopy(state)
    payload = event["payload"]
    if event["event_type"] == "transition":
        updated["current_state"] = payload.get("to_state", updated["current_state"])
    elif event["event_type"] == "cancellation_requested":
        updated["cancellation_state"] = "requested"
    updated["last_sequence"] = event["sequence"]
    updated["last_event_hash"] = event["event_hash"]
    return updated
