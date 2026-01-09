"""
Dashboard DTO definitions
Contract consistency: Fully aligned with site-hub, no Local-Core specific fields
"""

from typing import Optional, List, Dict, Any, Generic, TypeVar
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

T = TypeVar('T')


# ==================== Generic Pagination DTO ====================

class PaginatedResponse(BaseModel, Generic[T]):
    """Unified pagination response format (aligned with site-hub)"""
    items: List[T]
    total: int
    limit: int
    offset: int
    has_more: bool
    warnings: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ==================== Enum Definitions ====================

class InboxItemType(str, Enum):
    """Inbox item type (aligned with site-hub)"""
    PENDING_DECISION = "pending_decision"
    ASSIGNMENT = "assignment"
    MENTION = "mention"
    SYSTEM_ALERT = "system_alert"
    CASE_UPDATE = "case_update"


class WorkspaceSetupStatus(str, Enum):
    READY = "ready"
    NEEDS_SETUP = "needs_setup"
    PENDING = "pending"
    ERROR = "error"


class SetupItem(str, Enum):
    """Workspace setup item (aligned with site-hub)"""
    MODEL_CONFIG = "model_config"
    TOOL_AUTH = "tool_auth"
    PLAYBOOK_SELECTION = "playbook_selection"
    RUNTIME_PROFILE = "runtime_profile"
    COMPUTE_PROFILE = "compute_profile"
    CAPABILITY_PACK = "capability_pack"


class AssignmentReviewStatus(str, Enum):
    """Assignment review status (aligned with site-hub)"""
    NONE = "none"
    SUBMITTED = "submitted"
    NEEDS_CHANGES = "needs_changes"
    APPROVED = "approved"
    DELIVERED = "delivered"


# ==================== Dashboard Query ====================

class DashboardQuery(BaseModel):
    """Unified Dashboard query parameters (aligned with site-hub)"""
    scope: str = Field(default="global")
    view: str = Field(default="my_work")
    filters: Dict[str, Any] = Field(default_factory=dict)
    sort_by: str = Field(default="auto")
    sort_order: str = Field(default="desc")
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


# ==================== Summary DTO ====================

class DashboardCountsDTO(BaseModel):
    """
    Dashboard statistics counts (aligned with site-hub)

    Prohibited: Do not add Local-Core specific fields (e.g., needs_setup_count)
    """
    pending_decisions: int = 0
    open_assignments: int = 0
    open_cases: int = 0
    blocked_cases: int = 0
    running_jobs: int = 0
    overdue_items: int = 0
    mentions: int = 0
    delegated_pending: int = 0


class DashboardSummaryDTO(BaseModel):
    """Dashboard summary (aligned with site-hub)"""
    scope: str
    counts: DashboardCountsDTO
    recent_activity_at: Optional[datetime] = None
    needs_setup: List[SetupItem] = Field(default_factory=list)
    not_supported: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ==================== Inbox DTO ====================

class InboxItemDTO(BaseModel):
    """Inbox item (aligned with site-hub)"""
    id: str
    item_type: InboxItemType
    source_type: str
    source_id: str

    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    case_id: Optional[str] = None
    case_title: Optional[str] = None
    thread_id: Optional[str] = None

    title: str
    summary: Optional[str] = None
    status: str
    priority: int = 0
    is_overdue: bool = False
    due_at: Optional[datetime] = None

    assignee_user_id: Optional[str] = None
    assignee_name: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_by_name: Optional[str] = None

    available_actions: List[str] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)

    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== Case DTO ====================

class CaseCardDTO(BaseModel):
    """Case card (aligned with site-hub)"""
    id: str
    tenant_id: str
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None

    title: Optional[str] = None
    summary: Optional[str] = None
    status: str

    progress_percent: Optional[int] = None
    checklist_done: int = 0
    checklist_total: int = 0

    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None
    owner_avatar: Optional[str] = None
    assignees: List[Dict[str, str]] = Field(default_factory=list)

    priority: int = 0
    due_at: Optional[datetime] = None
    is_overdue: bool = False

    open_assignments_count: int = 0
    artifacts_count: int = 0
    threads_count: int = 0

    last_activity_type: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    last_activity_by: Optional[str] = None

    available_actions: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Assignment DTO ====================

class AssignmentCardDTO(BaseModel):
    """Assignment card (aligned with site-hub)"""
    id: str
    case_id: Optional[str] = None
    case_title: Optional[str] = None
    case_group_id: Optional[str] = None
    case_group_name: Optional[str] = None

    source_workspace_id: Optional[str] = None
    source_workspace_name: Optional[str] = None
    target_workspace_id: Optional[str] = None
    target_workspace_name: Optional[str] = None

    title: str
    description: Optional[str] = None
    status: str
    review_status: Optional[AssignmentReviewStatus] = None
    priority: int = 0

    claimed_by_user_id: Optional[str] = None
    claimed_by_name: Optional[str] = None
    claimed_by_avatar: Optional[str] = None
    delegated_by_user_id: Optional[str] = None
    delegated_by_name: Optional[str] = None
    delegated_by_avatar: Optional[str] = None

    due_at: Optional[datetime] = None
    is_overdue: bool = False

    required_artifacts: List[str] = Field(default_factory=list)
    submitted_artifacts: List[str] = Field(default_factory=list)

    available_actions: List[str] = Field(default_factory=list)

    hop_count: int = 1
    max_hops: int = 5
    routing_reason: Optional[str] = None

    created_at: datetime
    claimed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== Workspace DTO ====================

class WorkspaceCardDTO(BaseModel):
    """Workspace card (aligned with site-hub)"""
    id: str
    name: str
    description: Optional[str] = None

    setup_status: WorkspaceSetupStatus
    needs_setup_items: List[SetupItem] = Field(default_factory=list)

    boundary_type: str = "personal"

    open_cases_count: int = 0
    pending_decisions_count: int = 0
    running_jobs_count: int = 0

    last_activity_at: Optional[datetime] = None
    last_activity_type: Optional[str] = None

    members_count: int = 1
    current_user_role: Optional[str] = "owner"

    is_pinned: bool = False
    tags: List[str] = Field(default_factory=list)

    primary_action: Optional[Dict[str, Any]] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Saved View DTO ====================

class SavedViewDTO(BaseModel):
    """Saved view (aligned with site-hub)"""
    id: str
    name: str
    scope: str
    view: str
    tab: str = "inbox"
    filters: Dict[str, Any] = Field(default_factory=dict)
    sort_by: str = "auto"
    sort_order: str = "desc"
    is_default: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SavedViewCreate(BaseModel):
    """Create Saved View request"""
    name: str
    scope: str = "global"
    view: str = "my_work"
    tab: str = "inbox"
    filters: Dict[str, Any] = Field(default_factory=dict)
    sort_by: str = "auto"
    sort_order: str = "desc"
    is_default: bool = False
