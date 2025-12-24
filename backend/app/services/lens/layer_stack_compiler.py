"""Layer Stack Compiler - Compile LayerStack into executable context."""
import hashlib
import json
import logging
from typing import Dict, Any, List, Optional

from ...models.layer_stack import LayerStack, LayerItem
from ...models.mind_lens import LensSpec
from .lens_compiler import LensCompiler

logger = logging.getLogger(__name__)


class LayerStackCompiler:
    """
    Compile LayerStack into executable context.

    Takes a layer stack configuration and compiles it for a specific
    step/modality, merging all applicable layers.
    """

    def __init__(
        self,
        lens_compiler: Optional[LensCompiler] = None,
        lens_store: Optional[Any] = None
    ):
        """
        Initialize layer stack compiler.

        Args:
            lens_compiler: Lens compiler instance (creates new if None)
            lens_store: MindLensStore instance for loading LensSpecs (optional)
        """
        self.lens_compiler = lens_compiler or LensCompiler()
        self.lens_store = lens_store
        self._lens_spec_cache: Dict[str, LensSpec] = {}

    def compile(
        self,
        layer_stack: LayerStack,
        target_step: str,
        target_modality: str
    ) -> Dict[str, Any]:
        """
        Compile layer stack for specific step/modality.

        Args:
            layer_stack: Layer stack configuration
            target_step: Target step name
            target_modality: Target modality (text, image, audio, etc.)

        Returns:
            Compiled context with:
            - compiled_context: Merged context from all applicable layers
            - context_hash: Hash of compiled context for dependency tracking
            - layers_used: List of lens IDs that were used
        """
        # Get applicable layers (enabled and in scope)
        applicable_layers = self._get_applicable_layers(
            layer_stack.layers, target_step, target_modality
        )

        if not applicable_layers:
            logger.debug(
                f"No applicable layers for step {target_step}, "
                f"modality {target_modality}"
            )
            return {
                "compiled_context": {},
                "context_hash": self._generate_hash({}),
                "layers_used": []
            }

        # Sort by priority (higher first)
        applicable_layers.sort(key=lambda l: l.priority, reverse=True)

        # Compile each layer and merge
        compiled = {}
        layers_used = []

        for layer in applicable_layers:
            lens_spec = self._get_lens_spec(layer.lens_id)
            if not lens_spec:
                logger.warning(f"Lens spec not found for {layer.lens_id}, skipping")
                continue

            # Compile layer
            layer_compiled = self.lens_compiler.compile(
                lens_spec, layer.params, target_step, target_modality
            )

            if layer_compiled:
                # Merge with existing context (weighted if needed)
                compiled = self._merge_context(compiled, layer_compiled, layer.weight)
                layers_used.append(layer.lens_id)

        # Generate context hash
        context_hash = self._generate_hash(compiled)

        # Update layer stack cache
        layer_stack.compiled_context = compiled
        layer_stack.context_hash = context_hash

        logger.info(
            f"Compiled layer stack {layer_stack.stack_id} for step {target_step}, "
            f"modality {target_modality}: {len(layers_used)} layers used"
        )

        return {
            "compiled_context": compiled,
            "context_hash": context_hash,
            "layers_used": layers_used
        }

    def _get_applicable_layers(
        self,
        layers: List[LayerItem],
        target_step: str,
        target_modality: str
    ) -> List[LayerItem]:
        """
        Get layers that are enabled and in scope.

        Args:
            layers: List of layer items
            target_step: Target step name
            target_modality: Target modality

        Returns:
            List of applicable layers
        """
        applicable = []

        for layer in layers:
            if not layer.enabled:
                continue

            # Check scope
            if not self._is_in_scope(layer, target_step, target_modality):
                continue

            applicable.append(layer)

        return applicable

    def _is_in_scope(
        self,
        layer: LayerItem,
        target_step: str,
        target_modality: str
    ) -> bool:
        """
        Check if layer is in scope for target step/modality.

        Args:
            layer: Layer item
            target_step: Target step name
            target_modality: Target modality

        Returns:
            True if layer applies to target
        """
        # "all" scope means applies to everything
        if "all" in layer.scope:
            return True

        # Check if step or modality is in scope
        return target_step in layer.scope or target_modality in layer.scope

    def _merge_context(
        self,
        existing: Dict[str, Any],
        new_layer: Dict[str, Any],
        weight: float
    ) -> Dict[str, Any]:
        """
        Merge new layer context into existing context.

        Args:
            existing: Existing compiled context
            new_layer: New layer context to merge
            weight: Weight of new layer (0-1)

        Returns:
            Merged context
        """
        merged = existing.copy()

        # Merge system prompt additions (concatenate)
        if "system_prompt_additions" in new_layer:
            existing_system = merged.get("system_prompt_additions", "")
            new_system = new_layer["system_prompt_additions"]
            if existing_system:
                merged["system_prompt_additions"] = f"{existing_system}\n{new_system}"
            else:
                merged["system_prompt_additions"] = new_system

        # Merge style rules (append)
        if "style_rules" in new_layer:
            existing_rules = merged.get("style_rules", [])
            new_rules = new_layer["style_rules"]
            if isinstance(existing_rules, list) and isinstance(new_rules, list):
                merged["style_rules"] = existing_rules + new_rules
            else:
                merged["style_rules"] = new_rules

        # Merge prompt modifications (concatenate prefix/suffix)
        if "prompt_prefix" in new_layer:
            existing_prefix = merged.get("prompt_prefix", "")
            new_prefix = new_layer["prompt_prefix"]
            merged["prompt_prefix"] = f"{new_prefix}\n{existing_prefix}"

        if "prompt_suffix" in new_layer:
            existing_suffix = merged.get("prompt_suffix", "")
            new_suffix = new_layer["prompt_suffix"]
            merged["prompt_suffix"] = f"{existing_suffix}\n{new_suffix}"

        # Merge params (weighted average for numeric, override for others)
        if "params" in new_layer:
            existing_params = merged.get("params", {})
            new_params = new_layer["params"]
            merged["params"] = self._merge_params(existing_params, new_params, weight)

        # Merge transformer configs (append)
        if "transformer_configs" in new_layer:
            existing_transformers = merged.get("transformer_configs", {})
            new_transformers = new_layer["transformer_configs"]
            if isinstance(existing_transformers, dict) and isinstance(new_transformers, dict):
                merged["transformer_configs"] = {
                    **existing_transformers,
                    **new_transformers
                }
            else:
                merged["transformer_configs"] = new_transformers

        return merged

    def _merge_params(
        self,
        existing: Dict[str, Any],
        new_params: Dict[str, Any],
        weight: float
    ) -> Dict[str, Any]:
        """
        Merge parameters with weighted average for numeric values.

        Args:
            existing: Existing parameters
            new_params: New parameters
            weight: Weight of new parameters

        Returns:
            Merged parameters
        """
        merged = existing.copy()

        for key, value in new_params.items():
            if key in merged:
                # Weighted average for numeric values
                if isinstance(value, (int, float)) and isinstance(merged[key], (int, float)):
                    merged[key] = (1 - weight) * merged[key] + weight * value
                else:
                    # Override for non-numeric
                    merged[key] = value
            else:
                merged[key] = value

        return merged

    def _get_lens_spec(self, lens_id: str) -> Optional[LensSpec]:
        """
        Get lens spec by ID.

        Args:
            lens_id: Lens ID (may include version, e.g., "writer.hemingway@1.0.0")

        Returns:
            LensSpec or None if not found
        """
        # Check cache first
        if lens_id in self._lens_spec_cache:
            return self._lens_spec_cache[lens_id]

        # Load from store if available
        if self.lens_store:
            lens_spec = self.lens_store.get_lens_spec(lens_id)
            if lens_spec:
                self._lens_spec_cache[lens_id] = lens_spec
                return lens_spec

        logger.warning(f"Lens spec not found: {lens_id}")
        return None

    def _generate_hash(self, context: Dict[str, Any]) -> str:
        """
        Generate hash of compiled context.

        Args:
            context: Compiled context dictionary

        Returns:
            SHA256 hash as hex string
        """
        # Sort keys for consistent hashing
        sorted_context = json.dumps(context, sort_keys=True)
        return hashlib.sha256(sorted_context.encode()).hexdigest()[:16]

