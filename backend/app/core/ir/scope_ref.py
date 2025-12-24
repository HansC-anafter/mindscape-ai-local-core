"""
ScopeRef IR Schema

Intermediate representation for scope references (workspace/brand/site/env).
Used to pass scope information between stages.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum


class ScopeType(str, Enum):
    """Scope type"""
    WORKSPACE = "workspace"
    BRAND = "brand"
    SITE = "site"
    ENV = "env"
    PROJECT = "project"
    PHASE = "phase"


@dataclass
class ScopeRefIR:
    """
    ScopeRef IR Schema

    Structured intermediate representation for scope references.
    Used to pass scope information between stages:
    - Intent analysis stage → Scope resolution stage
    - Scope resolution stage → Plan generation stage
    - Plan generation stage → Tool execution stage
    """
    # Scope identification
    scope_type: ScopeType
    scope_id: str  # ID of the scope entity

    # Scope hierarchy (optional, for nested scopes)
    parent_scope: Optional["ScopeRefIR"] = None

    # Scope metadata
    name: Optional[str] = None  # Human-readable name
    description: Optional[str] = None

    # Scope-specific attributes
    attributes: Dict[str, Any] = None

    # Version for backward compatibility
    version: str = "1.0"

    # Additional metadata
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize default values"""
        if self.attributes is None:
            self.attributes = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "version": self.version,
            "scope_type": self.scope_type.value,
            "scope_id": self.scope_id,
            "attributes": self.attributes,
        }

        if self.name:
            result["name"] = self.name
        if self.description:
            result["description"] = self.description
        if self.parent_scope:
            result["parent_scope"] = self.parent_scope.to_dict()
        if self.metadata:
            result["metadata"] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScopeRefIR":
        """Create ScopeRefIR from dictionary"""
        scope_type = ScopeType(data["scope_type"])

        parent_scope = None
        if data.get("parent_scope"):
            parent_scope = cls.from_dict(data["parent_scope"])

        return cls(
            scope_type=scope_type,
            scope_id=data["scope_id"],
            name=data.get("name"),
            description=data.get("description"),
            attributes=data.get("attributes", {}),
            parent_scope=parent_scope,
            version=data.get("version", "1.0"),
            metadata=data.get("metadata"),
        )

    def get_full_path(self) -> str:
        """Get full scope path (e.g., 'workspace:123/brand:456/site:789')"""
        path_parts = [f"{self.scope_type.value}:{self.scope_id}"]
        current = self.parent_scope
        while current:
            path_parts.insert(0, f"{current.scope_type.value}:{current.scope_id}")
            current = current.parent_scope
        return "/".join(path_parts)





