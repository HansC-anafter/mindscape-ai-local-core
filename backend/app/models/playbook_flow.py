"""
Playbook Flow model for Project-based flow orchestration

A Playbook Flow defines a sequence of playbook executions within a Project,
with nodes representing playbooks and edges representing dependencies.

This enables multi-playbook orchestration where playbooks work together
to complete a larger deliverable.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class FlowNode(BaseModel):
    """
    Flow node - represents a playbook execution step

    Each node in a flow represents a playbook that needs to be executed,
    along with its configuration and dependencies.
    """

    id: str = Field(..., description="Unique node identifier")
    playbook_code: str = Field(..., description="Playbook code to execute")
    name: str = Field(..., description="Node display name")
    description: Optional[str] = Field(None, description="Node description")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Input parameters for this node")
    config: Dict[str, Any] = Field(default_factory=dict, description="Node-specific configuration")


class FlowEdge(BaseModel):
    """
    Flow edge - represents dependency between nodes

    Edges define the execution order: node B depends on node A
    if there's an edge from A to B.
    """

    from_node: str = Field(..., description="Source node ID")
    to_node: str = Field(..., description="Target node ID")
    condition: Optional[str] = Field(None, description="Optional condition for edge execution")
    artifact_mapping: Optional[Dict[str, str]] = Field(
        None,
        description="Artifact mapping: {from_artifact_id: to_artifact_id}"
    )


class PlaybookFlow(BaseModel):
    """
    Playbook Flow - defines a sequence of playbook executions

    A Flow consists of nodes (playbooks) and edges (dependencies),
    enabling orchestrated execution of multiple playbooks within a Project.
    """

    id: str = Field(..., description="Unique flow identifier")
    name: str = Field(..., description="Flow display name")
    description: Optional[str] = Field(None, description="Flow description")
    flow_definition: Dict[str, Any] = Field(
        ...,
        description="Flow definition containing nodes and edges"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

