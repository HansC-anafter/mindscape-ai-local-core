from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .reference_localization import ReferencePoint


class VectorizedReferenceSimilarityMatrix:
    """Compute scalar-equivalent feature similarities without Python pair loops."""

    def __init__(
        self,
        points: list[ReferencePoint],
        scales: Mapping[str, float],
    ) -> None:
        self.keys = sorted(
            {
                key
                for point in points
                for key in point.features
            }
        )
        self.point_values = np.asarray(
            [
                [float(point.features.get(key, 0.0)) for key in self.keys]
                for point in points
            ],
            dtype=np.float64,
        )
        self.point_presence = np.asarray(
            [
                [key in point.features for key in self.keys]
                for point in points
            ],
            dtype=bool,
        )
        self.scales = np.asarray(
            [max(0.001, float(scales.get(key, 0.05))) for key in self.keys],
            dtype=np.float64,
        )

    def __call__(
        self,
        history: list[dict[str, float]],
    ) -> list[list[float]]:
        if not history:
            return []
        learner_values = np.asarray(
            [
                [float(features.get(key, 0.0)) for key in self.keys]
                for features in history
            ],
            dtype=np.float64,
        )
        learner_presence = np.asarray(
            [[key in features for key in self.keys] for features in history],
            dtype=bool,
        )
        common = (
            learner_presence[:, np.newaxis, :]
            & self.point_presence[np.newaxis, :, :]
        )
        normalized = np.minimum(
            3.0,
            np.abs(
                learner_values[:, np.newaxis, :]
                - self.point_values[np.newaxis, :, :]
            )
            / self.scales[np.newaxis, np.newaxis, :],
        )
        counts = common.sum(axis=2)
        squared_sum = np.where(common, normalized * normalized, 0.0).sum(axis=2)
        mean_squared = np.divide(
            squared_sum,
            counts,
            out=np.zeros_like(squared_sum),
            where=counts > 0,
        )
        similarities = np.where(
            counts > 0,
            np.exp(-np.sqrt(mean_squared)),
            0.0,
        )
        return similarities.tolist()


__all__ = ["VectorizedReferenceSimilarityMatrix"]
