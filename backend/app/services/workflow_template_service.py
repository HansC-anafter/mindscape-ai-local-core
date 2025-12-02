"""
Workflow Template Service

Manages workflow templates, user-defined workflows, and template instantiation.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.app.models.workflow_template import (
    WorkflowTemplate,
    UserWorkflow,
    WorkflowVersion,
    WorkflowTemplateVariable,
    CreateWorkflowTemplateRequest,
    CreateUserWorkflowRequest,
    InstantiateTemplateRequest
)
from backend.app.models.playbook import HandoffPlan, WorkflowStep

logger = logging.getLogger(__name__)


class WorkflowTemplateService:
    """Service for managing workflow templates and user-defined workflows"""

    def __init__(self, templates_dir: Optional[Path] = None, workflows_dir: Optional[Path] = None):
        base_dir = Path(__file__).parent.parent.parent
        self.templates_dir = templates_dir or (base_dir / "workflow_templates")
        self.workflows_dir = workflows_dir or (base_dir / "user_workflows")
        self.versions_dir = self.workflows_dir / "versions"

        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(parents=True, exist_ok=True)

    def create_template(self, request: CreateWorkflowTemplateRequest) -> WorkflowTemplate:
        """
        Create a new workflow template

        Args:
            request: Template creation request

        Returns:
            Created WorkflowTemplate
        """
        steps = [WorkflowStep(**step_dict) for step_dict in request.steps]
        variables = {
            name: WorkflowTemplateVariable(**var_dict)
            for name, var_dict in request.variables.items()
        }

        template = WorkflowTemplate(
            template_id=request.template_id,
            name=request.name,
            description=request.description,
            category=request.category,
            tags=request.tags,
            steps=steps,
            variables=variables,
            context_template=request.context_template
        )

        self._save_template(template)
        logger.info(f"Created workflow template: {template.template_id}")
        return template

    def get_template(self, template_id: str) -> Optional[WorkflowTemplate]:
        """
        Get a workflow template by ID

        Args:
            template_id: Template identifier

        Returns:
            WorkflowTemplate if found, None otherwise
        """
        template_path = self.templates_dir / f"{template_id}.json"
        if not template_path.exists():
            return None

        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return WorkflowTemplate(**data)
        except Exception as e:
            logger.error(f"Failed to load template {template_id}: {e}")
            return None

    def list_templates(self, category: Optional[str] = None) -> List[WorkflowTemplate]:
        """
        List all workflow templates

        Args:
            category: Optional category filter

        Returns:
            List of WorkflowTemplate objects
        """
        templates = []
        for template_file in self.templates_dir.glob("*.json"):
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                template = WorkflowTemplate(**data)
                if category is None or template.category == category:
                    templates.append(template)
            except Exception as e:
                logger.warning(f"Failed to load template from {template_file}: {e}")

        return templates

    def instantiate_template(
        self,
        request: InstantiateTemplateRequest,
        workspace_id: str,
        profile_id: str
    ) -> HandoffPlan:
        """
        Instantiate a template into a HandoffPlan

        Args:
            request: Template instantiation request
            workspace_id: Workspace ID
            profile_id: User profile ID

        Returns:
            Instantiated HandoffPlan
        """
        template = self.get_template(request.template_id)
        if not template:
            raise ValueError(f"Template not found: {request.template_id}")

        for var_name, var_def in template.variables.items():
            if var_def.required and var_name not in request.variable_values:
                if var_def.default is None:
                    raise ValueError(f"Required template variable missing: {var_name}")
                request.variable_values[var_name] = var_def.default

        instantiated_steps = []
        for step in template.steps:
            instantiated_step = self._instantiate_step(step, request.variable_values)
            instantiated_steps.append(instantiated_step)

        context = template.context_template.copy()
        context.update(request.context_overrides)
        context.update({
            "workspace_id": workspace_id,
            "profile_id": profile_id,
            "template_id": request.template_id
        })

        return HandoffPlan(
            steps=instantiated_steps,
            context=context
        )

    def _instantiate_step(
        self,
        step: WorkflowStep,
        variable_values: Dict[str, Any]
    ) -> WorkflowStep:
        """Instantiate a single step with variable substitution"""
        instantiated_inputs = self._substitute_variables(step.inputs, variable_values)
        instantiated_input_mapping = self._substitute_variables(
            step.input_mapping,
            variable_values
        )
        instantiated_condition = None
        if step.condition:
            instantiated_condition = self._substitute_variables(
                step.condition,
                variable_values
            )

        return WorkflowStep(
            playbook_code=step.playbook_code,
            kind=step.kind,
            inputs=instantiated_inputs,
            input_mapping=instantiated_input_mapping,
            condition=instantiated_condition,
            interaction_mode=step.interaction_mode,
            retry_policy=step.retry_policy,
            error_handling=step.error_handling
        )

    def _substitute_variables(self, value: Any, variable_values: Dict[str, Any]) -> Any:
        """Recursively substitute template variables in a value"""
        if isinstance(value, str):
            for var_name, var_value in variable_values.items():
                placeholder = f"${{template.{var_name}}}"
                if placeholder in value:
                    value = value.replace(placeholder, str(var_value))
            return value
        elif isinstance(value, dict):
            return {
                k: self._substitute_variables(v, variable_values)
                for k, v in value.items()
            }
        elif isinstance(value, list):
            return [
                self._substitute_variables(item, variable_values)
                for item in value
            ]
        else:
            return value

    def create_user_workflow(
        self,
        request: CreateUserWorkflowRequest,
        workspace_id: str,
        profile_id: str
    ) -> UserWorkflow:
        """
        Create a user-defined workflow

        Args:
            request: User workflow creation request
            workspace_id: Workspace ID
            profile_id: User profile ID

        Returns:
            Created UserWorkflow
        """
        steps = [WorkflowStep(**step_dict) for step_dict in request.steps]

        workflow = UserWorkflow(
            workflow_id=request.workflow_id,
            name=request.name,
            description=request.description,
            template_id=request.template_id,
            steps=steps,
            context=request.context,
            workspace_id=workspace_id,
            profile_id=profile_id,
            is_public=request.is_public,
            tags=request.tags
        )

        self._save_user_workflow(workflow)
        self._create_workflow_version(workflow, profile_id, "Initial version")
        logger.info(f"Created user workflow: {workflow.workflow_id}")
        return workflow

    def get_user_workflow(
        self,
        workflow_id: str,
        workspace_id: Optional[str] = None
    ) -> Optional[UserWorkflow]:
        """
        Get a user-defined workflow by ID

        Args:
            workflow_id: Workflow identifier
            workspace_id: Optional workspace ID filter

        Returns:
            UserWorkflow if found, None otherwise
        """
        workflow_path = self.workflows_dir / f"{workflow_id}.json"
        if not workflow_path.exists():
            return None

        try:
            with open(workflow_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            workflow = UserWorkflow(**data)

            if workspace_id and workflow.workspace_id != workspace_id:
                return None

            return workflow
        except Exception as e:
            logger.error(f"Failed to load user workflow {workflow_id}: {e}")
            return None

    def list_user_workflows(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None
    ) -> List[UserWorkflow]:
        """
        List user-defined workflows

        Args:
            workspace_id: Optional workspace ID filter
            profile_id: Optional profile ID filter

        Returns:
            List of UserWorkflow objects
        """
        workflows = []
        for workflow_file in self.workflows_dir.glob("*.json"):
            try:
                with open(workflow_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                workflow = UserWorkflow(**data)

                if workspace_id and workflow.workspace_id != workspace_id:
                    continue
                if profile_id and workflow.profile_id != profile_id:
                    continue

                workflows.append(workflow)
            except Exception as e:
                logger.warning(f"Failed to load workflow from {workflow_file}: {e}")

        return workflows

    def update_user_workflow(
        self,
        workflow_id: str,
        updates: Dict[str, Any],
        profile_id: str,
        changelog: Optional[str] = None
    ) -> Optional[UserWorkflow]:
        """
        Update a user-defined workflow and create a new version

        Args:
            workflow_id: Workflow identifier
            updates: Dictionary of fields to update
            profile_id: User profile ID making the update
            changelog: Optional changelog for this version

        Returns:
            Updated UserWorkflow if found, None otherwise
        """
        workflow = self.get_user_workflow(workflow_id)
        if not workflow:
            return None

        if workflow.profile_id != profile_id:
            raise PermissionError("Only workflow owner can update workflow")

        if "steps" in updates:
            updates["steps"] = [WorkflowStep(**step_dict) for step_dict in updates["steps"]]

        for key, value in updates.items():
            if hasattr(workflow, key):
                setattr(workflow, key, value)

        workflow.updated_at = datetime.utcnow()
        workflow.version = self._increment_version(workflow.version)

        self._save_user_workflow(workflow)
        self._create_workflow_version(workflow, profile_id, changelog)
        logger.info(f"Updated user workflow: {workflow_id} to version {workflow.version}")
        return workflow

    def get_workflow_versions(self, workflow_id: str) -> List[WorkflowVersion]:
        """
        Get all versions of a workflow

        Args:
            workflow_id: Workflow identifier

        Returns:
            List of WorkflowVersion objects
        """
        versions = []
        version_files = self.versions_dir.glob(f"{workflow_id}_*.json")

        for version_file in version_files:
            try:
                with open(version_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                versions.append(WorkflowVersion(**data))
            except Exception as e:
                logger.warning(f"Failed to load version from {version_file}: {e}")

        versions.sort(key=lambda v: v.created_at, reverse=True)
        return versions

    def restore_workflow_version(
        self,
        workflow_id: str,
        version_id: str,
        profile_id: str
    ) -> Optional[UserWorkflow]:
        """
        Restore a workflow to a specific version

        Args:
            workflow_id: Workflow identifier
            version_id: Version identifier to restore
            profile_id: User profile ID

        Returns:
            Restored UserWorkflow if found, None otherwise
        """
        workflow = self.get_user_workflow(workflow_id)
        if not workflow:
            return None

        if workflow.profile_id != profile_id:
            raise PermissionError("Only workflow owner can restore workflow")

        versions = self.get_workflow_versions(workflow_id)
        target_version = next((v for v in versions if v.version_id == version_id), None)
        if not target_version:
            return None

        workflow.steps = target_version.steps
        workflow.context = target_version.context
        workflow.version = target_version.version
        workflow.updated_at = datetime.utcnow()

        self._save_user_workflow(workflow)
        self._create_workflow_version(
            workflow,
            profile_id,
            f"Restored to version {target_version.version}"
        )
        logger.info(f"Restored workflow {workflow_id} to version {target_version.version}")
        return workflow

    def _save_template(self, template: WorkflowTemplate):
        """Save template to disk"""
        template_path = self.templates_dir / f"{template.template_id}.json"
        with open(template_path, 'w', encoding='utf-8') as f:
            json.dump(template.dict(), f, indent=2, ensure_ascii=False, default=str)

    def _save_user_workflow(self, workflow: UserWorkflow):
        """Save user workflow to disk"""
        workflow_path = self.workflows_dir / f"{workflow.workflow_id}.json"
        with open(workflow_path, 'w', encoding='utf-8') as f:
            json.dump(workflow.dict(), f, indent=2, ensure_ascii=False, default=str)

    def _create_workflow_version(
        self,
        workflow: UserWorkflow,
        created_by: str,
        changelog: Optional[str] = None
    ):
        """Create a version record for a workflow"""
        version_id = str(uuid.uuid4())
        version = WorkflowVersion(
            version_id=version_id,
            workflow_id=workflow.workflow_id,
            version=workflow.version,
            steps=workflow.steps,
            context=workflow.context,
            changelog=changelog,
            created_by=created_by,
            is_current=True
        )

        version_path = self.versions_dir / f"{workflow.workflow_id}_{version_id}.json"
        with open(version_path, 'w', encoding='utf-8') as f:
            json.dump(version.dict(), f, indent=2, ensure_ascii=False, default=str)

        for existing_version in self.get_workflow_versions(workflow.workflow_id):
            if existing_version.version_id != version_id:
                existing_version.is_current = False
                existing_version_path = (
                    self.versions_dir / f"{workflow.workflow_id}_{existing_version.version_id}.json"
                )
                with open(existing_version_path, 'w', encoding='utf-8') as f:
                    json.dump(existing_version.dict(), f, indent=2, ensure_ascii=False, default=str)

    def _increment_version(self, current_version: str) -> str:
        """Increment version string (simple patch increment)"""
        parts = current_version.split('.')
        if len(parts) == 3:
            try:
                major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
                return f"{major}.{minor}.{patch + 1}"
            except ValueError:
                pass
        return f"{current_version}.1"

