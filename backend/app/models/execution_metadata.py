"""
ExecutionMetadata - standardized metadata structure for executions

Provides consistent metadata structure across different execution engines,
supporting intent/execution/cloud namespace separation.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ExecutionMetadata(BaseModel):
    """
    Standardized execution metadata structure

    Provides consistent metadata structure for cross-engine interoperability.
    Follows namespace separation: intent.*, execution.*, cloud.*
    """

    # Intent-related metadata
    intent: Optional[Dict[str, str]] = Field(
        None,
        description="Intent-related IDs: {intent_id, intent_instance_id}"
    )

    # Execution-related metadata
    execution: Optional[Dict[str, str]] = Field(
        None,
        description="Execution-related IDs: {playbook_code, playbook_execution_id, skill_id, skill_execution_id}"
    )

    # Cloud-related metadata
    cloud: Optional[Dict[str, str]] = Field(
        None,
        description="Cloud-related IDs: {tenant_id, cloud_workspace_id, job_id}"
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionMetadata":
        """
        Create ExecutionMetadata from existing metadata dictionary

        Supports backward compatibility with existing metadata structures.

        Args:
            data: Existing metadata dictionary

        Returns:
            ExecutionMetadata instance
        """
        if not data:
            return cls()

        # Extract intent namespace
        intent_data = {}
        if "intent_id" in data:
            intent_data["intent_id"] = data["intent_id"]
        if "intent_instance_id" in data:
            intent_data["intent_instance_id"] = data["intent_instance_id"]
        if "origin_intent_id" in data:
            intent_data["intent_id"] = data["origin_intent_id"]

        # Extract execution namespace
        execution_data = {}
        if "playbook_code" in data:
            execution_data["playbook_code"] = data["playbook_code"]
        if "playbook_execution_id" in data:
            execution_data["playbook_execution_id"] = data["playbook_execution_id"]
        if "execution_id" in data:
            execution_data["execution_id"] = data["execution_id"]
        if "skill_id" in data:
            execution_data["skill_id"] = data["skill_id"]
        if "skill_execution_id" in data:
            execution_data["skill_execution_id"] = data["skill_execution_id"]

        # Extract cloud namespace
        cloud_data = {}
        if "tenant_id" in data:
            cloud_data["tenant_id"] = data["tenant_id"]
        if "cloud_workspace_id" in data:
            cloud_data["cloud_workspace_id"] = data["cloud_workspace_id"]
        if "job_id" in data:
            cloud_data["job_id"] = data["job_id"]

        return cls(
            intent=intent_data if intent_data else None,
            execution=execution_data if execution_data else None,
            cloud=cloud_data if cloud_data else None
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format

        Flattens the namespaced structure back to a flat dictionary
        for compatibility with existing systems.

        Returns:
            Flattened metadata dictionary
        """
        result = {}

        if self.intent:
            result.update(self.intent)

        if self.execution:
            result.update(self.execution)

        if self.cloud:
            result.update(self.cloud)

        return result

    def get_intent_id(self) -> Optional[str]:
        """Get intent ID"""
        return self.intent.get("intent_id") if self.intent else None

    def get_intent_instance_id(self) -> Optional[str]:
        """Get intent instance ID"""
        return self.intent.get("intent_instance_id") if self.intent else None

    def get_playbook_code(self) -> Optional[str]:
        """Get playbook code"""
        return self.execution.get("playbook_code") if self.execution else None

    def get_playbook_execution_id(self) -> Optional[str]:
        """Get playbook execution ID"""
        return self.execution.get("playbook_execution_id") if self.execution else None

    def get_skill_id(self) -> Optional[str]:
        """Get skill ID"""
        return self.execution.get("skill_id") if self.execution else None

    def get_skill_execution_id(self) -> Optional[str]:
        """Get skill execution ID"""
        return self.execution.get("skill_execution_id") if self.execution else None

    def get_tenant_id(self) -> Optional[str]:
        """Get tenant ID"""
        return self.cloud.get("tenant_id") if self.cloud else None

    def get_cloud_workspace_id(self) -> Optional[str]:
        """Get cloud workspace ID"""
        return self.cloud.get("cloud_workspace_id") if self.cloud else None

    def get_job_id(self) -> Optional[str]:
        """Get job ID"""
        return self.cloud.get("job_id") if self.cloud else None

    def set_intent_context(self, intent_id: str, intent_instance_id: Optional[str] = None) -> None:
        """Set intent context"""
        if not self.intent:
            self.intent = {}
        self.intent["intent_id"] = intent_id
        if intent_instance_id:
            self.intent["intent_instance_id"] = intent_instance_id

    def set_execution_context(self, **kwargs) -> None:
        """Set execution context"""
        if not self.execution:
            self.execution = {}
        self.execution.update(kwargs)

    def set_cloud_context(self, **kwargs) -> None:
        """Set cloud context"""
        if not self.cloud:
            self.cloud = {}
        self.cloud.update(kwargs)

    def is_cloud_execution(self) -> bool:
        """Check if this is a cloud execution"""
        return self.cloud is not None and bool(self.cloud.get("tenant_id"))

    def is_playbook_execution(self) -> bool:
        """Check if this is a playbook execution"""
        return self.execution is not None and bool(self.execution.get("playbook_code"))

    def is_skill_execution(self) -> bool:
        """Check if this is a skill execution"""
        return self.execution is not None and bool(self.execution.get("skill_id"))
