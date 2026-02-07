"""
Break-glass Service

Provides time-limited, audited host access for external agents.
Break-glass permissions are granted via Decision Cards and expire after a configurable duration.
"""

import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BreakGlassStatus(str, Enum):
    """Break-glass permission status"""

    PENDING = "pending"  # Awaiting approval
    APPROVED = "approved"  # Approved, can be used
    ACTIVE = "active"  # Currently in use
    EXPIRED = "expired"  # Time limit exceeded
    REVOKED = "revoked"  # Manually revoked
    COMPLETED = "completed"  # Successfully completed


class HostOperation(str, Enum):
    """Allowed host operations via break-glass"""

    READ_FILE = "read_file"  # Read file outside sandbox
    WRITE_FILE = "write_file"  # Write file outside sandbox
    EXECUTE_COMMAND = "execute_command"  # Execute shell command
    NETWORK_ACCESS = "network_access"  # Access blocked network host
    INSTALL_PACKAGE = "install_package"  # Install system package
    ACCESS_SECRET = "access_secret"  # Access secret from vault


@dataclass
class BreakGlassPermission:
    """A break-glass permission grant"""

    permission_id: str
    workspace_id: str
    agent_id: str
    requested_by: str  # agent or system
    approved_by: Optional[str] = None  # user who approved

    # What operations are allowed
    operations: List[HostOperation] = field(default_factory=list)
    resource_patterns: List[str] = field(
        default_factory=list
    )  # e.g., ["/etc/hosts", "/var/log/*"]

    # Time constraints
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    duration_minutes: int = 15

    # Status tracking
    status: BreakGlassStatus = BreakGlassStatus.PENDING
    used_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Audit trail
    reason: str = ""
    task_description: str = ""
    decision_card_id: Optional[str] = None
    audit_log: List[Dict[str, Any]] = field(default_factory=list)

    def is_valid(self) -> bool:
        """Check if permission is still valid for use"""
        if self.status not in [BreakGlassStatus.APPROVED, BreakGlassStatus.ACTIVE]:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            self.status = BreakGlassStatus.EXPIRED
            return False
        return True

    def use(self, operation: HostOperation, resource: str) -> bool:
        """Attempt to use this permission for an operation"""
        if not self.is_valid():
            return False

        # Check operation is allowed
        if operation not in self.operations:
            self._audit(f"Denied: operation {operation} not in allowed list")
            return False

        # Check resource pattern matches
        if not self._matches_resource_pattern(resource):
            self._audit(f"Denied: resource {resource} doesn't match patterns")
            return False

        # Mark as active on first use
        if self.status == BreakGlassStatus.APPROVED:
            self.status = BreakGlassStatus.ACTIVE
            self.used_at = datetime.utcnow()

        self._audit(f"Allowed: {operation} on {resource}")
        return True

    def _matches_resource_pattern(self, resource: str) -> bool:
        """Check if resource matches any allowed pattern"""
        import fnmatch

        for pattern in self.resource_patterns:
            if fnmatch.fnmatch(resource, pattern):
                return True
        return False

    def _audit(self, message: str) -> None:
        """Add audit log entry"""
        self.audit_log.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "message": message,
            }
        )


class BreakGlassRequest(BaseModel):
    """Request for break-glass permission"""

    workspace_id: str
    agent_id: str
    operations: List[str] = Field(..., description="Requested operations")
    resource_patterns: List[str] = Field(..., description="Resource patterns to access")
    reason: str = Field(..., description="Why break-glass is needed")
    task_description: str = Field("", description="Task that requires break-glass")
    duration_minutes: int = Field(
        15, ge=5, le=60, description="Duration in minutes (5-60)"
    )


class BreakGlassApproval(BaseModel):
    """Approval for break-glass request"""

    permission_id: str
    approved: bool
    approved_by: str
    comment: Optional[str] = None
    modified_operations: Optional[List[str]] = None  # Can reduce scope
    modified_duration: Optional[int] = None  # Can reduce duration


class BreakGlassService:
    """
    Break-glass Service

    Manages temporary, audited permissions for host access.
    All break-glass actions are logged for security audit.
    """

    def __init__(self, store: Optional[Any] = None):
        """
        Initialize Break-glass Service.

        Args:
            store: Optional persistence store (defaults to in-memory)
        """
        self.store = store
        self._permissions: Dict[str, BreakGlassPermission] = {}
        self._workspace_permissions: Dict[str, List[str]] = (
            {}
        )  # workspace_id -> [permission_id]

    def request_permission(
        self,
        request: BreakGlassRequest,
    ) -> BreakGlassPermission:
        """
        Request break-glass permission.

        Creates a pending permission that requires user approval via Decision Card.

        Args:
            request: Break-glass request details

        Returns:
            BreakGlassPermission in PENDING status
        """
        # Generate permission ID
        permission_id = self._generate_permission_id(
            request.workspace_id,
            request.agent_id,
            request.reason,
        )

        # Parse operations
        operations = []
        for op_str in request.operations:
            try:
                operations.append(HostOperation(op_str))
            except ValueError:
                logger.warning(f"Unknown operation: {op_str}")

        # Create permission
        permission = BreakGlassPermission(
            permission_id=permission_id,
            workspace_id=request.workspace_id,
            agent_id=request.agent_id,
            requested_by=request.agent_id,
            operations=operations,
            resource_patterns=request.resource_patterns,
            duration_minutes=request.duration_minutes,
            reason=request.reason,
            task_description=request.task_description,
            status=BreakGlassStatus.PENDING,
        )

        # Store permission
        self._permissions[permission_id] = permission
        if request.workspace_id not in self._workspace_permissions:
            self._workspace_permissions[request.workspace_id] = []
        self._workspace_permissions[request.workspace_id].append(permission_id)

        # Create Decision Card for approval
        self._create_decision_card(permission)

        logger.info(
            f"Break-glass permission requested: {permission_id}, "
            f"workspace={request.workspace_id}, agent={request.agent_id}"
        )

        return permission

    def approve_permission(
        self,
        approval: BreakGlassApproval,
    ) -> Optional[BreakGlassPermission]:
        """
        Approve or deny a break-glass request.

        Args:
            approval: Approval details

        Returns:
            Updated permission or None if not found
        """
        permission = self._permissions.get(approval.permission_id)
        if not permission:
            logger.warning(f"Permission not found: {approval.permission_id}")
            return None

        if permission.status != BreakGlassStatus.PENDING:
            logger.warning(
                f"Permission not pending: {approval.permission_id} ({permission.status})"
            )
            return None

        if approval.approved:
            permission.status = BreakGlassStatus.APPROVED
            permission.approved_by = approval.approved_by

            # Apply modifications if any
            if approval.modified_operations:
                permission.operations = [
                    HostOperation(op)
                    for op in approval.modified_operations
                    if op in [o.value for o in permission.operations]  # Can only reduce
                ]
            if approval.modified_duration:
                permission.duration_minutes = min(
                    approval.modified_duration,
                    permission.duration_minutes,
                )

            # Set expiration
            permission.expires_at = datetime.utcnow() + timedelta(
                minutes=permission.duration_minutes
            )

            permission._audit(
                f"Approved by {approval.approved_by}, "
                f"expires at {permission.expires_at.isoformat()}"
            )

            logger.info(f"Break-glass approved: {approval.permission_id}")
        else:
            permission.status = BreakGlassStatus.REVOKED
            permission._audit(
                f"Denied by {approval.approved_by}: {approval.comment or 'No reason'}"
            )

            logger.info(f"Break-glass denied: {approval.permission_id}")

        return permission

    def get_permission(self, permission_id: str) -> Optional[BreakGlassPermission]:
        """Get a permission by ID"""
        return self._permissions.get(permission_id)

    def list_permissions(
        self,
        workspace_id: str,
        status: Optional[BreakGlassStatus] = None,
    ) -> List[BreakGlassPermission]:
        """List permissions for a workspace"""
        permission_ids = self._workspace_permissions.get(workspace_id, [])
        permissions = [
            self._permissions[pid] for pid in permission_ids if pid in self._permissions
        ]

        if status:
            permissions = [p for p in permissions if p.status == status]

        return permissions

    def check_permission(
        self,
        workspace_id: str,
        agent_id: str,
        operation: HostOperation,
        resource: str,
    ) -> Optional[BreakGlassPermission]:
        """
        Check if there's a valid break-glass permission for an operation.

        Args:
            workspace_id: Workspace ID
            agent_id: Agent requesting access
            operation: Operation to perform
            resource: Resource to access

        Returns:
            Valid permission if found, None otherwise
        """
        permission_ids = self._workspace_permissions.get(workspace_id, [])

        for pid in permission_ids:
            permission = self._permissions.get(pid)
            if not permission:
                continue

            if permission.agent_id != agent_id:
                continue

            if permission.use(operation, resource):
                return permission

        return None

    def revoke_permission(
        self,
        permission_id: str,
        revoked_by: str,
        reason: str = "",
    ) -> Optional[BreakGlassPermission]:
        """Revoke a permission"""
        permission = self._permissions.get(permission_id)
        if not permission:
            return None

        permission.status = BreakGlassStatus.REVOKED
        permission._audit(f"Revoked by {revoked_by}: {reason}")

        logger.info(f"Break-glass revoked: {permission_id}")
        return permission

    def complete_permission(
        self,
        permission_id: str,
    ) -> Optional[BreakGlassPermission]:
        """Mark a permission as completed (task finished)"""
        permission = self._permissions.get(permission_id)
        if not permission:
            return None

        if permission.status in [BreakGlassStatus.APPROVED, BreakGlassStatus.ACTIVE]:
            permission.status = BreakGlassStatus.COMPLETED
            permission.completed_at = datetime.utcnow()
            permission._audit("Completed successfully")

            logger.info(f"Break-glass completed: {permission_id}")

        return permission

    def cleanup_expired(self) -> int:
        """Clean up expired permissions"""
        count = 0
        now = datetime.utcnow()

        for permission in self._permissions.values():
            if permission.status in [
                BreakGlassStatus.APPROVED,
                BreakGlassStatus.ACTIVE,
            ]:
                if permission.expires_at and now > permission.expires_at:
                    permission.status = BreakGlassStatus.EXPIRED
                    permission._audit("Expired")
                    count += 1

        if count > 0:
            logger.info(f"Cleaned up {count} expired break-glass permissions")

        return count

    def _generate_permission_id(
        self,
        workspace_id: str,
        agent_id: str,
        reason: str,
    ) -> str:
        """Generate unique permission ID"""
        timestamp = datetime.utcnow().isoformat()
        data = f"{workspace_id}:{agent_id}:{reason}:{timestamp}"
        return f"bg_{hashlib.sha256(data.encode()).hexdigest()[:16]}"

    def _create_decision_card(self, permission: BreakGlassPermission) -> None:
        """Create a Decision Card for break-glass approval"""
        try:
            from backend.app.services.mindscape_store import MindscapeStore
            from backend.app.models.mindscape import IntentLog, EventType
            import uuid

            store = MindscapeStore()

            # Create IntentLog for the decision
            intent_log = IntentLog(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                profile_id="",
                workspace_id=permission.workspace_id,
                raw_input=f"Break-glass request: {permission.reason}",
                final_decision={
                    "decision_id": permission.permission_id,
                    "decision_type": "BREAK_GLASS",
                    "requires_user_approval": True,
                    "can_auto_execute": False,
                    "agent_id": permission.agent_id,
                    "operations": [op.value for op in permission.operations],
                    "resource_patterns": permission.resource_patterns,
                    "duration_minutes": permission.duration_minutes,
                    "reason": permission.reason,
                    "task_description": permission.task_description,
                },
                metadata={
                    "decision_method": "break_glass_service",
                    "permission_id": permission.permission_id,
                },
            )

            store.create_intent_log(intent_log)
            permission.decision_card_id = intent_log.id
            permission._audit(f"Decision card created: {intent_log.id}")

        except Exception as e:
            logger.error(f"Failed to create decision card: {e}", exc_info=True)


# Singleton instance
_break_glass_service: Optional[BreakGlassService] = None


def get_break_glass_service() -> BreakGlassService:
    """Get the singleton Break-glass service instance"""
    global _break_glass_service
    if _break_glass_service is None:
        _break_glass_service = BreakGlassService()
    return _break_glass_service
