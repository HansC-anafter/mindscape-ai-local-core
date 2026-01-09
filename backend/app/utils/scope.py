"""
Scope parsing and validation
Pluggable design: Local mode fully open, Cloud mode strict validation
"""

import os
import logging
from typing import Optional, Literal, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ParsedScope:
    """Parsed scope object"""
    type: Literal["global", "workspace", "group"]
    id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class ScopeValidationResult:
    """Scope validation result"""
    is_valid: bool
    effective_scope: ParsedScope
    error_code: Optional[int] = None
    error_message: Optional[str] = None


def is_cloud_mode() -> bool:
    """Detect if running in Cloud mode"""
    return bool(os.getenv("SITE_HUB_API_BASE"))


def parse_scope(scope: Optional[str]) -> ParsedScope:
    """
    Parse scope string

    Format:
    - None or "global" -> global scope
    - "workspace:{id}" -> workspace scope
    - "group:{id}" -> group scope
    """
    if not scope or scope == "global":
        return ParsedScope(type="global")

    if ":" not in scope:
        return ParsedScope(
            type="global",
            warnings=[f"Invalid scope format: {scope}, falling back to global"]
        )

    parts = scope.split(":", 1)
    scope_type, scope_id = parts[0], parts[1] if len(parts) > 1 else ""

    if scope_type == "workspace":
        if not scope_id:
            return ParsedScope(
                type="global",
                warnings=["Empty workspace ID, falling back to global"]
            )
        return ParsedScope(type="workspace", id=scope_id)

    if scope_type == "group":
        if not scope_id:
            return ParsedScope(
                type="global",
                warnings=["Empty group ID, falling back to global"]
            )
        return ParsedScope(type="group", id=scope_id)

    return ParsedScope(
        type="global",
        warnings=[f"Unknown scope type: {scope_type}"]
    )


def validate_scope(
    scope: ParsedScope,
    auth: "AuthContext"
) -> ScopeValidationResult:
    """
    Validate scope access permissions

    Hard rules:
    - R4: Local mode group -> downgrade to global
    - R5: No workspace_ids when workspace scope -> 403
    """
    # Global scope: always allowed
    if scope.type == "global":
        return ScopeValidationResult(
            is_valid=True,
            effective_scope=scope
        )

    # Workspace scope
    if scope.type == "workspace":
        # R5: Check if user has access to the workspace
        if not auth.workspace_ids:
            # No workspace access -> 403
            return ScopeValidationResult(
                is_valid=False,
                effective_scope=scope,
                error_code=403,
                error_message=f"No workspace access for user {auth.user_id}"
            )

        if scope.id not in auth.workspace_ids:
            return ScopeValidationResult(
                is_valid=False,
                effective_scope=scope,
                error_code=403,
                error_message=f"User {auth.user_id} does not have access to workspace {scope.id}"
            )

        return ScopeValidationResult(
            is_valid=True,
            effective_scope=scope
        )

    # Group scope
    if scope.type == "group":
        if not is_cloud_mode():
            # R4: Local mode -> downgrade to global
            return ScopeValidationResult(
                is_valid=True,
                effective_scope=ParsedScope(
                    type="global",
                    warnings=[f"Group scope not supported in Local mode, falling back to global"]
                )
            )

        # Cloud mode: strict validation
        if not auth.group_ids:
            return ScopeValidationResult(
                is_valid=False,
                effective_scope=scope,
                error_code=403,
                error_message=f"No group access for user {auth.user_id}"
            )

        if scope.id not in auth.group_ids:
            return ScopeValidationResult(
                is_valid=False,
                effective_scope=scope,
                error_code=403,
                error_message=f"User {auth.user_id} does not have access to group {scope.id}"
            )

        return ScopeValidationResult(
            is_valid=True,
            effective_scope=scope
        )

    # Unknown type
    return ScopeValidationResult(
        is_valid=True,
        effective_scope=ParsedScope(type="global")
    )
