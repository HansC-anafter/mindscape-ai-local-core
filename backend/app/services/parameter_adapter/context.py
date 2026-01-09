"""
Execution Context Management

Manages execution context (workspace_id, profile_id, project_id, etc.)
and provides context injection for parameter adaptation.

Responsibilities:
- Context data structure definition
- Context building from various sources
- Context parameter mapping
- Not responsible for:
  - Parameter transformation (delegated to strategies)
  - Context validation (delegated to validators)
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """
    Execution context containing runtime information

    This is a data structure, not a service. It holds context data
    but doesn't perform transformations.
    """
    workspace_id: Optional[str] = None
    profile_id: Optional[str] = None
    project_id: Optional[str] = None
    execution_id: Optional[str] = None
    tenant_id: Optional[str] = None
    actor_id: Optional[str] = None
    subject_user_id: Optional[str] = None
    additional_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary"""
        return {
            "workspace_id": self.workspace_id,
            "profile_id": self.profile_id,
            "project_id": self.project_id,
            "execution_id": self.execution_id,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "subject_user_id": self.subject_user_id,
            **self.additional_context
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get context value by key"""
        if hasattr(self, key):
            return getattr(self, key)
        return self.additional_context.get(key, default)


class ExecutionContextBuilder:
    """
    Builder for creating ExecutionContext from various sources

    Responsibilities:
    - Building context from workflow parameters
    - Mapping workflow parameters to context fields
    - Extracting context from different sources
    - Not responsible for:
      - Context validation
      - Parameter transformation
    """

    @staticmethod
    def from_workflow_params(
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        **additional_params
    ) -> ExecutionContext:
        """
        Build execution context from workflow parameters

        Args:
            workspace_id: Workspace identifier
            profile_id: Profile/user identifier
            project_id: Project identifier
            execution_id: Execution identifier
            **additional_params: Additional context parameters

        Returns:
            ExecutionContext instance
        """
        return ExecutionContext(
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
            execution_id=execution_id,
            additional_context=additional_params
        )

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> ExecutionContext:
        """
        Build execution context from dictionary

        Args:
            data: Dictionary containing context data

        Returns:
            ExecutionContext instance
        """
        # Extract known fields
        known_fields = {
            "workspace_id", "profile_id", "project_id", "execution_id",
            "tenant_id", "actor_id", "subject_user_id"
        }

        context_data = {k: v for k, v in data.items() if k in known_fields}
        additional = {k: v for k, v in data.items() if k not in known_fields}

        return ExecutionContext(
            **context_data,
            additional_context=additional
        )

    @staticmethod
    def with_mapping(
        context: ExecutionContext,
        mapping: Dict[str, str]
    ) -> ExecutionContext:
        """
        Apply field mapping to context

        Args:
            context: Source execution context
            mapping: Mapping from source field to target field

        Returns:
            New ExecutionContext with mapped fields
        """
        mapped_data = {}
        for source_field, target_field in mapping.items():
            value = context.get(source_field)
            if value is not None:
                mapped_data[target_field] = value

        # Merge with existing context
        result = ExecutionContext(
            workspace_id=context.workspace_id,
            profile_id=context.profile_id,
            project_id=context.project_id,
            execution_id=context.execution_id,
            tenant_id=context.tenant_id or mapped_data.get("tenant_id"),
            actor_id=context.actor_id or mapped_data.get("actor_id"),
            subject_user_id=context.subject_user_id or mapped_data.get("subject_user_id"),
            additional_context={**context.additional_context, **mapped_data}
        )

        return result

