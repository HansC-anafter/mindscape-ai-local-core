"""
Template Engine for Workflow Orchestration

Handles template variable resolution in playbook-internal and workflow-level contexts.
Playbook-internal: {{input.xxx}}, {{step.xxx.yyy}}, {{context.xxx}} in playbook.json
Workflow-level: $previous.xxx.outputs.yyy, $context.xxx in HandoffPlan input_mapping
"""

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TemplateEngine:
    """
    Template engine for resolving variables in playbook.json and HandoffPlan

    Two-layer semantics:
    - Playbook-internal: {{input.xxx}}, {{step.xxx.yyy}}, {{context.xxx}}
      Used within a single playbook's steps
    - Workflow-level: $previous.xxx.outputs.yyy, $context.xxx
      Used for mapping between different playbooks in HandoffPlan
    """

    # Pattern for playbook-internal templates: {{input.xxx}}, {{step.xxx.yyy}}, {{context.xxx}}
    PLAYBOOK_TEMPLATE_PATTERN = re.compile(r'\{\{([^}]+)\}\}')

    # Pattern for workflow-level templates: $previous.xxx.outputs.yyy, $context.xxx
    WORKFLOW_TEMPLATE_PATTERN = re.compile(r'\$(\w+)\.([^.\s]+)(?:\.([^.\s]+))?(?:\.([^.\s]+))?')

    @staticmethod
    def resolve_playbook_template(
        template: str,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        workflow_context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Resolve playbook-internal template variables

        Supports:
        - {{input.xxx}} or {{input.xxx[0]}} - playbook inputs
        - {{step.xxx.yyy}} - step outputs
        - {{context.xxx}} - workflow context

        Args:
            template: Template string (can be nested dict/list)
            playbook_inputs: Playbook input values
            step_outputs: Dict of {step_id: {output_name: value}}
            workflow_context: Optional workflow context

        Returns:
            Resolved value (same structure as template, with variables replaced)
        """
        if workflow_context is None:
            workflow_context = {}

        def resolve_value(value: Any) -> Any:
            """Recursively resolve template variables"""
            if isinstance(value, str):
                return TemplateEngine._resolve_playbook_string(
                    value, playbook_inputs, step_outputs, workflow_context
                )
            elif isinstance(value, dict):
                return {k: resolve_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [resolve_value(item) for item in value]
            else:
                return value

        return resolve_value(template)

    @staticmethod
    def _resolve_playbook_string(
        template_str: str,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        workflow_context: Dict[str, Any]
    ) -> Any:
        """Resolve a single template string"""
        # Check if template_str is exactly a single variable (e.g., "{{step.xxx.yyy}}")
        # In this case, return the raw value (list/dict) instead of converting to string
        exact_match = TemplateEngine.PLAYBOOK_TEMPLATE_PATTERN.fullmatch(template_str.strip())
        if exact_match:
            var_expr = exact_match.group(1).strip()
            parts = var_expr.split('.')
            if len(parts) >= 1:
                var_type = parts[0]
                var_path = '.'.join(parts[1:]) if len(parts) > 1 else ""

                # Handle {{step.xxx.yyy}}
                if var_type == 'step':
                    step_parts = var_path.split('.', 1)
                    if len(step_parts) >= 2:
                        step_id, output_path = step_parts[0], step_parts[1]
                        step_result = step_outputs.get(step_id, {})
                        value = step_result
                        path_parts = output_path.split('.')
                        for part in path_parts:
                            if '[' in part:
                                key, index_str = part.split('[')
                                index = int(index_str.rstrip(']'))
                                if isinstance(value, dict):
                                    value = value.get(key)
                                if isinstance(value, list) and 0 <= index < len(value):
                                    value = value[index]
                                else:
                                    value = None
                                    break
                            else:
                                if isinstance(value, dict):
                                    value = value.get(part)
                                else:
                                    value = None
                                    break
                            if value is None:
                                break
                        # Return raw value for exact match (preserves list/dict types)
                        if value is not None:
                            return value

                # Handle {{input.xxx}}
                elif var_type == 'input':
                    value = playbook_inputs
                    for part in var_path.split('.'):
                        if '[' in part:
                            key, index_str = part.split('[')
                            index = int(index_str.rstrip(']'))
                            if isinstance(value, dict):
                                value = value.get(key)
                            if isinstance(value, list) and 0 <= index < len(value):
                                value = value[index]
                            else:
                                value = None
                                break
                        else:
                            value = value.get(part) if isinstance(value, dict) else None
                        if value is None:
                            break
                    # Return raw value for exact match (preserves list/dict types)
                    if value is not None:
                        return value

        if '{{step.' in template_str or '{{input.' in template_str:
            logger.debug(f"TemplateEngine: Resolving template string (length={len(template_str)}): {template_str[:200]}...")
        def replace_var(match):
            var_expr = match.group(1).strip()

            # Parse variable expression
            parts = var_expr.split('.')
            if len(parts) < 1:
                logger.warning(f"Invalid template variable: {var_expr}")
                return match.group(0)

            var_type = parts[0]
            var_path = '.'.join(parts[1:]) if len(parts) > 1 else ""

            # Handle {{input.xxx}} or {{input.xxx[0]}}
            if var_type == 'input':
                value = playbook_inputs
                for part in var_path.split('.'):
                    if '[' in part:
                        # Handle array indexing: xxx[0]
                        key, index_str = part.split('[')
                        index = int(index_str.rstrip(']'))
                        if isinstance(value, dict):
                            value = value.get(key)
                        if isinstance(value, list) and 0 <= index < len(value):
                            value = value[index]
                        else:
                            value = None
                    else:
                        value = value.get(part) if isinstance(value, dict) else None
                    if value is None:
                        break
                # Convert to string for template replacement
                if value is not None:
                    if isinstance(value, list):
                        # For lists, join with comma and space for better readability in prompts
                        return ', '.join(str(item) for item in value)
                    elif isinstance(value, dict):
                        import json
                        return json.dumps(value, ensure_ascii=False)
                    else:
                        return str(value)
                logger.warning(f"Template variable {{input.{var_path}}} resolved to None, using empty string")
                return ""

            # Handle {{step.xxx.yyy}} or {{step.xxx.yyy[0]}}
            elif var_type == 'step':
                step_parts = var_path.split('.', 1)
                if len(step_parts) < 2:
                    logger.warning(f"Invalid step reference: {var_expr}")
                    return match.group(0)
                step_id, output_path = step_parts[0], step_parts[1]
                step_result = step_outputs.get(step_id, {})
                logger.debug(f"TemplateEngine: Resolving {{step.{var_expr}}}: step_id={step_id}, output_path={output_path}, step_result_keys={list(step_result.keys()) if isinstance(step_result, dict) else 'N/A'}")

                # Handle nested paths and array indexing: output_name.xxx[0].yyy
                value = step_result
                path_parts = output_path.split('.')
                for part in path_parts:
                    if '[' in part:
                        # Handle array indexing: xxx[0]
                        key, index_str = part.split('[')
                        index = int(index_str.rstrip(']'))
                        if isinstance(value, dict):
                            value = value.get(key)
                        if isinstance(value, list) and 0 <= index < len(value):
                            value = value[index]
                        else:
                            value = None
                            break
                    else:
                        if isinstance(value, dict):
                            value = value.get(part)
                        else:
                            value = None
                            break
                    if value is None:
                        break

                if value is None or value == match.group(0):
                    logger.warning(f"TemplateEngine: Failed to resolve {{step.{var_expr}}}: step_id={step_id}, output_path={output_path} not found in step_result")
                    return match.group(0)

                value_type = type(value).__name__
                value_preview = str(value)[:200] if not isinstance(value, (dict, list)) else f"{value_type}(len={len(value) if hasattr(value, '__len__') else 'N/A'})"
                logger.debug(f"TemplateEngine: Resolved {{step.{var_expr}}} to {value_type}: {value_preview}")

                # Convert to string for template replacement
                if isinstance(value, list):
                    # For lists, join with comma and space for better readability in prompts
                    return ', '.join(str(item) for item in value)
                elif isinstance(value, dict):
                    import json
                    return json.dumps(value, ensure_ascii=False)
                else:
                    return str(value)

            elif var_type == 'item':
                loop_context = step_outputs.get("_loop", {})
                item = loop_context.get("item")
                if item is None:
                    return match.group(0)

                if var_path == "":
                    if isinstance(item, (dict, list)):
                        import json
                        return json.dumps(item, ensure_ascii=False)
                    return str(item)
                else:
                    value = item
                    for part in var_path.split('.'):
                        if isinstance(value, dict):
                            value = value.get(part)
                        elif isinstance(value, list) and part.isdigit():
                            value = value[int(part)] if int(part) < len(value) else None
                        else:
                            value = None
                            break
                        if value is None:
                            break

                    if value is not None:
                        if isinstance(value, (dict, list)):
                            import json
                            return json.dumps(value, ensure_ascii=False)
                        return str(value)
                    return match.group(0)
            elif var_type == 'index':
                loop_context = step_outputs.get("_loop", {})
                if var_path == "":
                    return str(loop_context.get("index", match.group(0)))
                return match.group(0)

            # Handle {{context.xxx}}
            elif var_type == 'context':
                return workflow_context.get(var_path, match.group(0))

            else:
                logger.warning(f"Unknown template variable type: {var_type}")
                return match.group(0)

        # Replace all template variables
        result = TemplateEngine.PLAYBOOK_TEMPLATE_PATTERN.sub(replace_var, template_str)

        # Try to parse as JSON if it looks like a JSON value
        if result.startswith('[') or result.startswith('{'):
            try:
                import json
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                pass

        return result

    @staticmethod
    def resolve_workflow_mapping(
        mapping: str,
        previous_results: Dict[str, Dict[str, Any]],
        workflow_context: Dict[str, Any]
    ) -> Any:
        """
        Resolve workflow-level mapping (for HandoffPlan input_mapping)

        Supports:
        - $previous.xxx.outputs.yyy - previous playbook outputs
        - $context.xxx - workflow context

        Args:
            mapping: Mapping expression (e.g., "$previous.pdf_ocr.outputs.ocr_text")
            previous_results: Dict of {playbook_code: {output_name: value}}
            workflow_context: Workflow context

        Returns:
            Resolved value
        """
        def replace_var(match):
            var_type = match.group(1)

            if var_type == 'previous':
                # $previous.xxx.outputs.yyy
                playbook_code = match.group(2)
                if match.group(3) == 'outputs' and match.group(4):
                    output_name = match.group(4)
                    playbook_result = previous_results.get(playbook_code, {})
                    return playbook_result.get(output_name, match.group(0))
                else:
                    logger.warning(f"Invalid previous reference: {mapping}")
                    return match.group(0)

            elif var_type == 'context':
                # $context.xxx
                context_key = match.group(2)
                return workflow_context.get(context_key, match.group(0))

            else:
                logger.warning(f"Unknown workflow variable type: {var_type}")
                return match.group(0)

        # Replace workflow template variables
        result = TemplateEngine.WORKFLOW_TEMPLATE_PATTERN.sub(replace_var, mapping)
        return result

    @staticmethod
    def prepare_playbook_inputs(
        step: Any,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        workflow_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Prepare step inputs by resolving all template variables

        Args:
            step: PlaybookStep with template variables in inputs
            playbook_inputs: Playbook input values
            step_outputs: Completed step outputs
            workflow_context: Optional workflow context

        Returns:
            Resolved inputs dict
        """
        return TemplateEngine.resolve_playbook_template(
            step.inputs,
            playbook_inputs,
            step_outputs,
            workflow_context
        )

    @staticmethod
    def prepare_workflow_step_inputs(
        step: Any,
        previous_results: Dict[str, Dict[str, Any]],
        workflow_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Prepare workflow step inputs by resolving input_mapping

        Args:
            step: WorkflowStep with input_mapping
            previous_results: Previous playbook execution results
            workflow_context: Workflow context

        Returns:
            Resolved inputs dict (merged with step.inputs)
        """
        resolved_inputs = step.inputs.copy()

        # Resolve input_mapping
        for input_name, mapping in step.input_mapping.items():
            resolved_value = TemplateEngine.resolve_workflow_mapping(
                mapping,
                previous_results,
                workflow_context
            )
            resolved_inputs[input_name] = resolved_value

        return resolved_inputs

