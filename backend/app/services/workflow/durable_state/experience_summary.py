"""Rebuildable, non-authoritative product-iteration experience summary."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical_json import encode, sha256_hex


def build_experience_summary(
    *,
    iteration_projection: dict[str, Any],
    claims: list[dict[str, Any]],
    synthesizer: dict[str, str],
) -> dict[str, Any]:
    definition = iteration_projection.get("definition")
    evaluation = iteration_projection.get("evaluation")
    if not definition or not evaluation:
        raise ValueError(
            "experience summary requires definition and evaluation"
        )
    accepted = set(
        iteration_projection.get("accepted_observation_ids", [])
    )
    normalized: list[dict[str, Any]] = []
    for claim in claims:
        sources = claim.get("source_observation_ids")
        if (
            not isinstance(sources, list)
            or not sources
            or any(source not in accepted for source in sources)
        ):
            raise ValueError(
                "experience claim requires accepted observation sources"
            )
        normalized.append(
            {
                "claim_id": str(claim["claim_id"]),
                "kind": str(claim["kind"]),
                "text": str(claim["text"]),
                "source_observation_ids": sorted(set(sources)),
                "provenance_sha256": str(claim["provenance_sha256"]),
            }
        )
    summary = {
        "iteration_id": definition["iteration_id"],
        "revision": definition["revision"],
        "frontier_sequence": evaluation["frontier_sequence"],
        "frontier_hash": evaluation["frontier_hash"],
        "evaluation_id": evaluation["evaluation_id"],
        "claims": sorted(normalized, key=lambda item: item["claim_id"]),
        "synthesizer": {
            "model_version": str(synthesizer["model_version"]),
            "prompt_version": str(synthesizer["prompt_version"]),
        },
        "generated_sequence": iteration_projection["last_sequence"],
        "authority": "projection_only",
    }
    encode(summary)
    return {
        **deepcopy(summary),
        "projection_sha256": sha256_hex(summary),
    }
