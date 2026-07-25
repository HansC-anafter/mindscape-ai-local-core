"""Effect-free plans for upper re-evaluation and iteration forks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical_json import sha256_hex
from .product_iteration_contract import (
    product_iteration_definition_sha256,
    require_definition,
)

FORKABLE_FIELDS = {
    "objective",
    "arms",
    "cohort",
    "metric_definitions",
    "validation_design",
    "evaluator",
    "observation_window",
    "budget",
    "release_target",
}


def plan_re_evaluation(
    *,
    iteration_state: dict[str, Any],
    current_sequence: int,
    evaluation_attempt_id: str,
    evaluator: dict[str, Any],
    authorized_lane: str,
) -> dict[str, Any]:
    definition = iteration_state.get("definition")
    if not definition:
        raise ValueError("re-evaluation requires an iteration definition")
    if iteration_state.get("current_state") not in {
        "evidence_ready",
        "decision_pending",
    }:
        raise ValueError(
            "re-evaluation requires evidence_ready or decision_pending state"
        )
    if evaluator != definition["evaluator"]:
        raise ValueError(
            "changed evaluator identity requires a successor iteration fork"
        )
    attempts = int(iteration_state.get("evaluation_attempt_count", 0))
    maximum = int(definition["budget"]["max_evaluation_attempts"])
    if attempts >= maximum:
        raise ValueError("iteration evaluation attempt budget is exhausted")
    if not evaluation_attempt_id or not authorized_lane:
        raise ValueError(
            "re-evaluation requires an attempt ID and authorized lane"
        )
    frontier = deepcopy(iteration_state["evidence_frontier"])
    intent = {
        "task_type": "product_outcome_re_evaluation",
        "iteration_id": definition["iteration_id"],
        "definition_sha256": definition["definition_sha256"],
        "expected_sequence": current_sequence,
        "evaluation_attempt_id": evaluation_attempt_id,
        "evaluator": deepcopy(evaluator),
        "evidence_frontier": frontier,
        "source_observation_ids": list(
            iteration_state.get("accepted_observation_ids", [])
        ),
        "authorized_lane": authorized_lane,
        "lower_execution_policy": "do_not_dispatch",
        "effect_policy": "no_external_effect",
    }
    return {
        **intent,
        "idempotency_key": (
            f"product-outcome-re-evaluation:{sha256_hex(intent)}"
        ),
    }


def plan_iteration_fork(
    *,
    source_state: dict[str, Any],
    new_iteration_id: str,
    new_revision: int,
    changes: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    source = source_state.get("definition")
    if not source:
        raise ValueError("iteration fork requires a source definition")
    if (
        not new_iteration_id
        or new_iteration_id == source["iteration_id"]
    ):
        raise ValueError("iteration fork requires a new iteration ID")
    if new_revision != int(source["revision"]) + 1:
        raise ValueError("iteration fork revision must advance by one")
    unknown = set(changes) - FORKABLE_FIELDS
    if not changes or unknown:
        raise ValueError(
            "iteration fork changes must use the exact mutable field set"
        )
    draft = deepcopy(source)
    draft.update(deepcopy(changes))
    draft.update(
        {
            "iteration_id": new_iteration_id,
            "revision": new_revision,
            "parent_iteration_id": source["iteration_id"],
            "state": "draft",
            "evidence_frontier": {
                "last_observation_sequence": 0,
                "frontier_hash": "0" * 64,
            },
            "created_at": created_at,
        }
    )
    draft.pop("admitted_at", None)
    draft["definition_sha256"] = (
        product_iteration_definition_sha256(draft)
    )
    require_definition(draft, state="draft")
    source_evaluation = source_state.get("evaluation")
    source_refs = {
        "parent_iteration_id": source["iteration_id"],
        "parent_definition_sha256": source["definition_sha256"],
        "parent_evidence_frontier": deepcopy(
            source_state.get("evidence_frontier")
        ),
        "parent_evaluation_sha256": (
            sha256_hex(source_evaluation)
            if source_evaluation
            else None
        ),
    }
    return {
        "draft_definition": draft,
        "changed_fields": sorted(changes),
        "source_refs": source_refs,
        "source_mutation_policy": "do_not_reopen",
    }
