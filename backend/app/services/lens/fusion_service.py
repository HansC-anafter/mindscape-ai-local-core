"""Lens Fusion service for combining multiple lenses."""
from typing import Dict, List, Optional
import logging

from ...models.lens_composition import (
    LensComposition,
    FusedLensContext,
    LensReference,
    LensModality
)
from ...models.mind_lens import MindLensInstance

logger = logging.getLogger(__name__)


class FusionService:
    """Service for fusing multiple lenses."""

    def fuse_composition(
        self,
        composition: LensComposition,
        lens_instances: Dict[str, MindLensInstance]
    ) -> FusedLensContext:
        """
        Fuse a composition into a single lens context.

        Args:
            composition: Composition to fuse
            lens_instances: Dictionary mapping lens_instance_id to MindLensInstance

        Returns:
            Fused lens context
        """
        strategy = composition.fusion_strategy

        if strategy == "priority":
            return self._priority_fusion(composition, lens_instances)
        elif strategy == "weighted":
            return self._weighted_fusion(composition, lens_instances)
        elif strategy == "priority_then_weighted":
            return self._priority_then_weighted_fusion(composition, lens_instances)
        else:
            logger.warning(f"Unknown fusion strategy: {strategy}, using priority_then_weighted")
            return self._priority_then_weighted_fusion(composition, lens_instances)

    def _priority_fusion(
        self,
        composition: LensComposition,
        lens_instances: Dict[str, MindLensInstance]
    ) -> FusedLensContext:
        """Fuse using priority only (highest priority wins)."""
        if not composition.lens_stack:
            raise ValueError("Composition lens_stack is empty")

        sorted_lenses = sorted(
            composition.lens_stack,
            key=lambda l: l.priority,
            reverse=True
        )

        highest_priority = sorted_lenses[0].priority
        top_lenses = [l for l in sorted_lenses if l.priority == highest_priority]

        if len(top_lenses) == 1:
            lens_ref = top_lenses[0]
            lens_instance = lens_instances.get(lens_ref.lens_instance_id)
            if not lens_instance:
                raise ValueError(f"Lens instance {lens_ref.lens_instance_id} not found")

            return FusedLensContext(
                composition_id=composition.composition_id,
                fused_values=lens_instance.values,
                source_lenses=[lens_ref.lens_instance_id],
                fusion_log=[{
                    "strategy": "priority",
                    "selected_lens": lens_ref.lens_instance_id,
                    "priority": lens_ref.priority
                }],
                fusion_strategy="priority"
            )
        else:
            return self._weighted_fusion_for_lenses(top_lenses, lens_instances, composition)

    def _weighted_fusion(
        self,
        composition: LensComposition,
        lens_instances: Dict[str, MindLensInstance]
    ) -> FusedLensContext:
        """Fuse using weighted average."""
        return self._weighted_fusion_for_lenses(
            composition.lens_stack,
            lens_instances,
            composition
        )

    def _priority_then_weighted_fusion(
        self,
        composition: LensComposition,
        lens_instances: Dict[str, MindLensInstance]
    ) -> FusedLensContext:
        """Fuse using priority first, then weighted average for same priority."""
        if not composition.lens_stack:
            raise ValueError("Composition lens_stack is empty")

        sorted_lenses = sorted(
            composition.lens_stack,
            key=lambda l: (l.priority, -l.weight),
            reverse=True
        )

        highest_priority = sorted_lenses[0].priority
        top_lenses = [l for l in sorted_lenses if l.priority == highest_priority]

        return self._weighted_fusion_for_lenses(top_lenses, lens_instances, composition)

    def _weighted_fusion_for_lenses(
        self,
        lens_refs: List[LensReference],
        lens_instances: Dict[str, MindLensInstance],
        composition: LensComposition
    ) -> FusedLensContext:
        """Helper method for weighted fusion."""
        if not lens_refs:
            raise ValueError("No lenses to fuse")

        total_weight = sum(l.weight for l in lens_refs)
        if total_weight == 0:
            raise ValueError("Total weight is zero")

        fused_values: Dict = {}
        fusion_log = []

        for lens_ref in lens_refs:
            lens_instance = lens_instances.get(lens_ref.lens_instance_id)
            if not lens_instance:
                logger.warning(f"Lens instance {lens_ref.lens_instance_id} not found, skipping")
                continue

            normalized_weight = lens_ref.weight / total_weight
            fusion_log.append({
                "lens_id": lens_ref.lens_instance_id,
                "weight": lens_ref.weight,
                "normalized_weight": normalized_weight
            })

            for key, value in lens_instance.values.items():
                if key not in fused_values:
                    fused_values[key] = 0.0

                if isinstance(value, (int, float)):
                    fused_values[key] += value * normalized_weight
                elif isinstance(value, str):
                    if key not in fused_values or not isinstance(fused_values[key], str):
                        fused_values[key] = value
                else:
                    fused_values[key] = value

        return FusedLensContext(
            composition_id=composition.composition_id,
            fused_values=fused_values,
            source_lenses=[l.lens_instance_id for l in lens_refs],
            fusion_log=fusion_log,
            fusion_strategy=composition.fusion_strategy
        )







