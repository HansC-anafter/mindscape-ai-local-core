"""
Workflow Step Loop Handler

Handles loop/iteration execution for playbook steps with for_each field.
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class WorkflowStepLoop:
    """Handles loop execution for workflow steps"""

    def __init__(self, template_engine, tool_executor, store=None):
        self.template_engine = template_engine
        self.tool_executor = tool_executor
        self.store = store

    def resolve_array_path(self, array_path: str, playbook_inputs: Dict[str, Any], step_outputs: Dict[str, Dict[str, Any]]) -> List[Any]:
        """
        Resolve array path (e.g., "step.search_photos.photos") to actual array

        Args:
            array_path: Path to array (e.g., "step.search_photos.photos")
            playbook_inputs: Playbook input values
            step_outputs: Completed step outputs

        Returns:
            List of items to iterate over
        """
        parts = array_path.split('.')
        if len(parts) < 2:
            raise ValueError(f"Invalid array path: {array_path}")

        if parts[0] == 'step':
            # step.xxx.yyy format
            step_id = parts[1]
            field_path = '.'.join(parts[2:]) if len(parts) > 2 else None

            step_result = step_outputs.get(step_id, {})
            if field_path:
                # Navigate nested structure
                value = step_result
                for part in field_path.split('.'):
                    if isinstance(value, dict):
                        value = value.get(part)
                    elif isinstance(value, list) and part.isdigit():
                        value = value[int(part)]
                    else:
                        value = None
                        break
                    if value is None:
                        break
            else:
                # Use entire step result (if it's a list)
                value = step_result

            if not isinstance(value, list):
                raise ValueError(f"Path '{array_path}' must resolve to a list, got {type(value)}")
            return value
        elif parts[0] == 'input':
            # input.xxx format
            input_name = parts[1]
            value = playbook_inputs.get(input_name)
            if not isinstance(value, list):
                raise ValueError(f"Input '{input_name}' must be a list, got {type(value)}")
            return value
        else:
            raise ValueError(f"Unsupported array path type: {parts[0]}")

    async def execute_step_with_loop(
        self,
        step: Any,
        execute_single_step_func,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        playbook_input_defs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0
    ) -> Dict[str, Any]:
        """
        Execute a step with loop support (for_each)

        Args:
            step: PlaybookStep with for_each field
            execute_single_step_func: Function to execute single step iteration
            playbook_inputs: Playbook input values
            step_outputs: Completed step outputs
            playbook_input_defs: Playbook input definitions

        Returns:
            Dict with array of results from each iteration
        """
        array_path = step.for_each
        array_value = self.resolve_array_path(array_path, playbook_inputs, step_outputs)

        if len(array_value) == 0:
            logger.warning(f"Step {step.id}: for_each array is empty, returning empty results")
            return {"results": [], "count": 0}

        logger.info(f"Step {step.id}: Executing loop with {len(array_value)} items")

        # Execute step for each item
        loop_results = []
        for index, item in enumerate(array_value):
            logger.debug(f"Step {step.id}: Executing iteration {index + 1}/{len(array_value)}")

            # Create temporary step_outputs with loop context
            temp_step_outputs = step_outputs.copy()
            temp_step_outputs["_loop"] = {
                "item": item,
                "index": index,
                "total": len(array_value)
            }

            # Execute single step with item context
            try:
                item_result = await execute_single_step_func(
                    step=step,
                    playbook_inputs=playbook_inputs,
                    step_outputs=temp_step_outputs,
                    playbook_input_defs=playbook_input_defs,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                    step_index=step_index
                )
                loop_results.append(item_result)
            except Exception as e:
                # Avoid recursion in error logging - use simple error message
                error_msg = str(e)[:500] if len(str(e)) > 500 else str(e)
                logger.error(f"Step {step.id}: Iteration {index + 1} failed: {error_msg}")
                # Continue with other items, but record the error
                loop_results.append({
                    "success": False,
                    "error": error_msg,
                    "index": index
                })

        # Aggregate results
        return {
            "results": loop_results,
            "count": len(loop_results),
            "success_count": sum(1 for r in loop_results if r.get("success", True))
        }

