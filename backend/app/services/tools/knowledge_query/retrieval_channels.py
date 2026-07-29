"""Deterministic channel admission and rank-fusion policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


MAX_ACTIVE_CHANNELS = 4


@dataclass(frozen=True)
class AdmittedRetrievalChannel:
    channel_id: str
    modality: str
    calibration_revision: Optional[str]


def select_admitted_channels(
    channels: Iterable[AdmittedRetrievalChannel],
    *,
    modality_filter: Optional[str],
) -> tuple[AdmittedRetrievalChannel, ...]:
    selected = tuple(
        sorted(
            (
                channel
                for channel in channels
                if modality_filter is None
                or channel.modality == modality_filter
            ),
            key=lambda channel: (
                channel.modality,
                channel.channel_id,
                channel.calibration_revision or "",
            ),
        )
    )
    if len(selected) > MAX_ACTIVE_CHANNELS:
        raise ValueError("knowledge_query_active_channel_limit_exceeded")
    return selected


def reciprocal_rank_fusion(
    ranked_ids: Iterable[Iterable[str]],
    *,
    rrf_k: int = 60,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in ranked_ids:
        for rank, identity in enumerate(ranking, start=1):
            scores[identity] = scores.get(identity, 0.0) + (
                1.0 / (rrf_k + rank)
            )
    return scores


__all__ = [
    "AdmittedRetrievalChannel",
    "MAX_ACTIVE_CHANNELS",
    "reciprocal_rank_fusion",
    "select_admitted_channels",
]
