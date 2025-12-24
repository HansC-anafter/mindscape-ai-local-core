"""
Complete Workflow System for IG Post

Orchestrates multiple playbooks in sequence to execute
end-to-end workflows for IG post creation and management.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class CompleteWorkflow:
    """
    Orchestrates complete workflows by chaining multiple playbooks

    Supports:
    - Multi-playbook orchestration
    - End-to-end workflow execution
    - Workflow state management
    - Error handling and rollback
    """

    def __init__(self, workspace_storage: WorkspaceStorage):
        """
        Initialize Complete Workflow System

        Args:
            workspace_storage: WorkspaceStorage instance
        """
        self.storage = workspace_storage
        self.workspace_id = workspace_storage.workspace_id

    def execute_workflow(
        self,
        workflow_name: str,
        workflow_steps: List[Dict[str, Any]],
        initial_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a complete workflow with multiple playbook steps

        Args:
            workflow_name: Name of the workflow
            workflow_steps: List of workflow steps, each containing:
                - playbook_code: Playbook to execute
                - inputs: Input parameters for the playbook
                - condition: Optional condition to check before execution
            initial_context: Initial context variables

        Returns:
            Workflow execution result with step results
        """
        context = initial_context or {}
        step_results = []
        workflow_status = "success"
        error_message = None

        for i, step in enumerate(workflow_steps, 1):
            step_name = step.get("name", f"step_{i}")
            playbook_code = step.get("playbook_code")
            step_inputs = step.get("inputs", {})
            condition = step.get("condition")

            if not playbook_code:
                logger.warning(f"Step {step_name} missing playbook_code, skipping")
                continue

            if condition:
                if not self._evaluate_condition(condition, context):
                    logger.info(f"Step {step_name} condition not met, skipping")
                    step_results.append({
                        "step_name": step_name,
                        "status": "skipped",
                        "reason": "condition_not_met"
                    })
                    continue

            try:
                # Update inputs to use workspace_id instead of vault_path
                resolved_inputs = self._resolve_variables(step_inputs, context)
                resolved_inputs = self._update_inputs_for_workspace(resolved_inputs)

                step_result = self._execute_playbook_step(
                    playbook_code=playbook_code,
                    inputs=resolved_inputs,
                    context=context
                )

                step_results.append({
                    "step_name": step_name,
                    "playbook_code": playbook_code,
                    "status": "success",
                    "result": step_result
                })

                if step.get("output_mapping"):
                    self._update_context_from_outputs(
                        context,
                        step_result,
                        step["output_mapping"]
                    )

            except Exception as e:
                logger.error(f"Step {step_name} failed: {e}", exc_info=True)
                workflow_status = "failed"
                error_message = str(e)

                step_results.append({
                    "step_name": step_name,
                    "playbook_code": playbook_code,
                    "status": "failed",
                    "error": str(e)
                })

                if step.get("on_error") == "stop":
                    break

        return {
            "workflow_name": workflow_name,
            "status": workflow_status,
            "error_message": error_message,
            "step_results": step_results,
            "final_context": context,
            "executed_at": datetime.now().isoformat()
        }

    def create_post_workflow(
        self,
        post_content: str,
        post_metadata: Dict[str, Any],
        target_folder: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute complete workflow for creating a new IG post

        Args:
            post_content: Post content
            post_metadata: Post metadata (frontmatter)
            target_folder: Target folder for post (optional)

        Returns:
            Workflow execution result
        """
        workflow_steps = [
            {
                "name": "validate_structure",
                "playbook_code": "ig_vault_structure_manager",
                "inputs": {
                    "action": "validate",
                    "workspace_id": self.workspace_id
                }
            },
            {
                "name": "generate_hashtags",
                "playbook_code": "ig_hashtag_manager",
                "inputs": {
                    "action": "combine_hashtags",
                    "workspace_id": self.workspace_id,
                    "hashtag_groups": post_metadata.get("hashtag_groups", [])
                }
            },
            {
                "name": "validate_assets",
                "playbook_code": "ig_asset_manager",
                "inputs": {
                    "action": "validate_assets",
                    "workspace_id": self.workspace_id,
                    "post_folder": "{{post_folder}}",
                    "required_assets": post_metadata.get("required_assets", [])
                },
                "condition": "{{post_folder}}"
            }
        ]

        initial_context = {
            "post_content": post_content,
            "post_metadata": post_metadata,
            "target_folder": target_folder
        }

        return self.execute_workflow(
            workflow_name="create_post",
            workflow_steps=workflow_steps,
            initial_context=initial_context
        )

    def review_workflow(
        self,
        post_path: str,
        review_notes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Execute complete workflow for reviewing and updating a post

        Args:
            post_path: Path to post file (relative to workspace or Obsidian-style)
            review_notes: List of review notes

        Returns:
            Workflow execution result
        """
        workflow_steps = [
            {
                "name": "add_review_notes",
                "playbook_code": "ig_review_system",
                "inputs": {
                    "action": "add_review_note",
                    "workspace_id": self.workspace_id,
                    "post_path": post_path,
                    "reviewer": "{{reviewer}}",
                    "note": "{{note}}",
                    "priority": "{{priority}}"
                }
            }
        ]

        initial_context = {
            "post_path": post_path,
            "review_notes": review_notes
        }

        return self.execute_workflow(
            workflow_name="review_post",
            workflow_steps=workflow_steps,
            initial_context=initial_context
        )

    def _update_inputs_for_workspace(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update inputs to use workspace_id instead of vault_path

        Args:
            inputs: Input dictionary

        Returns:
            Updated inputs dictionary
        """
        updated = inputs.copy()

        # Replace vault_path with workspace_id
        if "vault_path" in updated:
            vault_path = updated.pop("vault_path")
            if "workspace_id" not in updated:
                updated["workspace_id"] = self.workspace_id
            if "workspace_path" not in updated:
                # Keep workspace_path for backward compatibility
                updated["workspace_path"] = vault_path

        # Ensure workspace_id is set
        if "workspace_id" not in updated:
            updated["workspace_id"] = self.workspace_id

        return updated

    def _execute_playbook_step(
        self,
        playbook_code: str,
        inputs: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single playbook step

        Note: This is a placeholder implementation.
        In production, this would call the actual playbook execution engine.
        """
        logger.info(f"Executing playbook: {playbook_code} with inputs: {list(inputs.keys())}")

        return {
            "playbook_code": playbook_code,
            "inputs": inputs,
            "outputs": {},
            "executed_at": datetime.now().isoformat()
        }

    def _resolve_variables(
        self,
        inputs: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Resolve template variables in inputs using context

        Args:
            inputs: Input dictionary with potential template variables
            context: Context dictionary with variable values

        Returns:
            Resolved inputs dictionary
        """
        resolved = {}

        for key, value in inputs.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                var_name = value[2:-2].strip()
                resolved[key] = context.get(var_name, value)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_variables(value, context)
            elif isinstance(value, list):
                resolved[key] = [
                    self._resolve_variables(item, context) if isinstance(item, dict)
                    else (context.get(item[2:-2].strip(), item) if isinstance(item, str) and item.startswith("{{") and item.endswith("}}") else item)
                    for item in value
                ]
            else:
                resolved[key] = value

        return resolved

    def _evaluate_condition(
        self,
        condition: str,
        context: Dict[str, Any]
    ) -> bool:
        """
        Evaluate a condition string using context

        Args:
            condition: Condition string (e.g., "{{variable}} == 'value'")
            context: Context dictionary

        Returns:
            Boolean result of condition evaluation
        """
        try:
            resolved_condition = self._resolve_variables({"cond": condition}, context)["cond"]
            return bool(eval(resolved_condition, {"__builtins__": {}}, {}))
        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return False

    def _update_context_from_outputs(
        self,
        context: Dict[str, Any],
        step_result: Dict[str, Any],
        output_mapping: Dict[str, str]
    ) -> None:
        """
        Update context with outputs from a step

        Args:
            context: Context dictionary to update
            step_result: Step execution result
            output_mapping: Mapping of output keys to context variable names
        """
        outputs = step_result.get("outputs", {})

        for output_key, context_var in output_mapping.items():
            if output_key in outputs:
                context[context_var] = outputs[output_key]

