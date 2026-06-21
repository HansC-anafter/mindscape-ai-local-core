"""Composition graph installed contract and node provider models."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.models.object_runtime.composition_graph_common import (
    CompositionGraphDiagnostic,
    CompositionGraphPortDirection,
)


class CompositionGraphPort(BaseModel):
    """Typed connection point for a graph node type."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    direction: CompositionGraphPortDirection
    label: Optional[str] = None
    data_type: str = Field(default="any", min_length=1)
    required: bool = False
    accepted_object_roles: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphNodeType(BaseModel):
    """Node type exposed by core or by an installed capability contract."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    source: Literal["core", "pack"] = "pack"
    capability_code: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    input_ports: List[CompositionGraphPort] = Field(default_factory=list)
    output_ports: List[CompositionGraphPort] = Field(default_factory=list)
    payload_schema: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_ports(self) -> "CompositionGraphNodeType":
        for port in self.input_ports:
            if port.direction != "input":
                raise ValueError("input_ports entries must use direction=input")
        for port in self.output_ports:
            if port.direction != "output":
                raise ValueError("output_ports entries must use direction=output")
        return self


class CompositionGraphEdgeType(BaseModel):
    """Edge type exposed by an installed capability contract."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    source_data_type: str = "any"
    target_data_type: str = "any"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphCompileTarget(BaseModel):
    """Pack-owned callable used for graph compilation."""

    model_config = ConfigDict(extra="forbid")

    backend: str = Field(min_length=1)
    output_mode: Literal["meeting_command_envelope", "run_harness_spec"] = (
        "meeting_command_envelope"
    )


class CompositionGraphNodeExecutorTarget(BaseModel):
    """Pack-owned callable used for executable composition graph nodes."""

    model_config = ConfigDict(extra="forbid")

    backend: str = Field(min_length=1)


class CompositionGraphNodeOptionSource(BaseModel):
    """Pack-owned callable used for server-side node option resolution."""

    model_config = ConfigDict(extra="forbid")

    backend: str = Field(min_length=1)


class CompositionGraphNodeRuntimeLock(BaseModel):
    """In-process concurrency lock declared by a pack node provider."""

    model_config = ConfigDict(extra="forbid")

    key_template: str = Field(min_length=1)
    max_parallel: Literal[1] = 1


class CompositionGraphNodeProviderNode(CompositionGraphNodeType):
    """Executable pack node type exposed through composition_graph_nodes."""

    executor: CompositionGraphNodeExecutorTarget
    option_sources: Dict[str, CompositionGraphNodeOptionSource] = Field(
        default_factory=dict
    )
    runtime_lock: Optional[CompositionGraphNodeRuntimeLock] = None


class CompositionGraphNodeProviderContract(BaseModel):
    """Installed pack executable node provider contract."""

    model_config = ConfigDict(extra="forbid")

    capability_code: str = Field(min_length=1)
    label: str = Field(min_length=1)
    enabled: bool = True
    contract_version: str = Field(min_length=1)
    nodes: List[CompositionGraphNodeProviderNode] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphNodeOption(BaseModel):
    """Single server-resolved option for a graph node payload field."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)
    label: str = Field(min_length=1)
    disabled: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphNodeOptionsResponse(BaseModel):
    """Server-side node option resolution response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    node_type: str = Field(min_length=1)
    field: str = Field(min_length=1)
    options: List[CompositionGraphNodeOption] = Field(default_factory=list)
    diagnostics: List[CompositionGraphDiagnostic] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompositionGraphContract(BaseModel):
    """Installed pack graph contract normalized for the workbench UI."""

    model_config = ConfigDict(extra="forbid")

    capability_code: str = Field(min_length=1)
    label: str = Field(min_length=1)
    enabled: bool = True
    contract_version: str = Field(min_length=1)
    accepted_object_roles: List[str] = Field(default_factory=list)
    node_types: List[CompositionGraphNodeType] = Field(default_factory=list)
    edge_types: List[CompositionGraphEdgeType] = Field(default_factory=list)
    compile: Optional[CompositionGraphCompileTarget] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_pack_node_ownership(self) -> "CompositionGraphContract":
        for node_type in self.node_types:
            if node_type.id == "object_reference":
                raise ValueError("object_reference is core-owned and cannot be declared by packs")
        return self


__all__ = [
    "CompositionGraphCompileTarget",
    "CompositionGraphContract",
    "CompositionGraphEdgeType",
    "CompositionGraphNodeExecutorTarget",
    "CompositionGraphNodeOption",
    "CompositionGraphNodeOptionsResponse",
    "CompositionGraphNodeOptionSource",
    "CompositionGraphNodeProviderContract",
    "CompositionGraphNodeProviderNode",
    "CompositionGraphNodeRuntimeLock",
    "CompositionGraphNodeType",
    "CompositionGraphPort",
]
