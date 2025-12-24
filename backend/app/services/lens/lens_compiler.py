"""Lens Compiler - Compile LensSpec into executable context."""
import logging
from typing import Dict, Any, Optional

from ...models.mind_lens import LensSpec

logger = logging.getLogger(__name__)


class LensCompiler:
    """
    Compile LensSpec into executable context.

    Lens is not just a label, but a compilable execution context.
    It can inject prompts, style rules, and transformers into steps.
    """

    def compile(
        self,
        lens_spec: LensSpec,
        params: Dict[str, Any],
        target_step: str,
        target_modality: str
    ) -> Dict[str, Any]:
        """
        Compile lens into executable context.

        Args:
            lens_spec: Lens specification to compile
            params: Parameters for lens customization
            target_step: Target step name
            target_modality: Target modality (text, image, audio, etc.)

        Returns:
            Compiled context with:
            - system_prompt_additions: Additional system prompt text
            - style_rules: Style rules to apply
            - prompt_modifications: Prompt prefix/suffix modifications
            - transformer_configs: Transformer configurations (if any)
            - params: Applied parameters
        """
        # Check if lens applies to target modality
        if target_modality not in lens_spec.applies_to:
            logger.debug(
                f"Lens {lens_spec.lens_id} does not apply to modality {target_modality}"
            )
            return {}

        compiled = {}

        # Inject system prompt
        if "system" in lens_spec.inject:
            compiled["system_prompt_additions"] = lens_spec.inject["system"]

        # Apply style rules
        if "style_rules" in lens_spec.inject:
            compiled["style_rules"] = lens_spec.inject["style_rules"]

        # Apply prompt modifications
        if "prompt_prefix" in lens_spec.inject:
            compiled["prompt_prefix"] = lens_spec.inject["prompt_prefix"]

        if "prompt_suffix" in lens_spec.inject:
            compiled["prompt_suffix"] = lens_spec.inject["prompt_suffix"]

        # Apply parameters
        if lens_spec.params_schema:
            compiled["params"] = self._apply_params(lens_spec.params_schema, params)

        # Apply transformers (if any)
        if lens_spec.transformers:
            compiled["transformer_configs"] = {
                "transformers": lens_spec.transformers,
                "enabled": True
            }

        logger.debug(
            f"Compiled lens {lens_spec.lens_id} for step {target_step}, "
            f"modality {target_modality}"
        )

        return compiled

    def _apply_params(
        self,
        params_schema: Dict[str, Any],
        provided_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply parameters according to schema.

        Args:
            params_schema: Parameter schema definition
            provided_params: Provided parameter values

        Returns:
            Applied parameters with defaults
        """
        applied = {}

        for param_name, param_def in params_schema.items():
            if param_name in provided_params:
                value = provided_params[param_name]
                # Validate value if schema has constraints
                if isinstance(param_def, dict):
                    if "type" in param_def:
                        value = self._validate_and_convert(value, param_def)
                    if "min" in param_def and value < param_def["min"]:
                        value = param_def["min"]
                    if "max" in param_def and value > param_def["max"]:
                        value = param_def["max"]
                applied[param_name] = value
            elif isinstance(param_def, dict) and "default" in param_def:
                applied[param_name] = param_def["default"]

        return applied

    def _validate_and_convert(
        self,
        value: Any,
        param_def: Dict[str, Any]
    ) -> Any:
        """Validate and convert parameter value."""
        param_type = param_def.get("type", "string")

        if param_type == "float":
            return float(value)
        elif param_type == "int":
            return int(value)
        elif param_type == "bool":
            return bool(value)
        else:
            return str(value)


