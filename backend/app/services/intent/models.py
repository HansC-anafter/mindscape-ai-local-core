"""
Intent Models and Enums

Core data structures for intent analysis pipeline.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime


class InteractionType(str, Enum):
    """Layer 1: Interaction type classification"""

    QA = "qa"  # Pure Q&A (no playbook needed)
    START_PLAYBOOK = "start_playbook"  # User wants to start/continue a playbook
    MANAGE_SETTINGS = "manage_settings"  # User wants to manage settings
    UNKNOWN = "unknown"  # Cannot determine


class TaskDomain(str, Enum):
    """Layer 2: Task domain classification"""

    PROPOSAL_WRITING = "proposal_writing"  # Writing proposals, grant applications
    YEARLY_REVIEW = "yearly_review"  # Annual review, yearly book compilation
    HABIT_LEARNING = "habit_learning"  # Habit organization, habit learning
    PROJECT_PLANNING = "project_planning"  # Project planning, task breakdown
    CONTENT_WRITING = "content_writing"  # Content writing, copywriting
    UNKNOWN = "unknown"  # Unknown domain


class IntentAnalysisResult:
    """Result of 3-layer intent analysis"""

    def __init__(self):
        # Layer 1 results
        self.interaction_type: Optional[InteractionType] = None
        self.interaction_confidence: float = 0.0

        # Layer 2 results
        self.task_domain: Optional[TaskDomain] = None
        self.task_domain_confidence: float = 0.0

        # Layer 3 results
        self.selected_playbook_code: Optional[str] = None
        self.playbook_confidence: float = 0.0
        self.playbook_context: Dict[str, Any] = {}
        self.handoff_plan: Optional[Any] = (
            None  # HandoffPlan from playbook.run (new architecture)
        )

        # Multi-step workflow support
        self.is_multi_step: bool = False
        self.workflow_steps: List[Dict[str, Any]] = []
        self.step_dependencies: Dict[str, List[str]] = {}

        # Metadata
        self.raw_input: str = ""
        self.channel: str = "api"
        self.profile_id: Optional[str] = None
        self.project_id: Optional[str] = None
        self.workspace_id: Optional[str] = None
        self.pipeline_steps: Dict[str, Any] = {}
        self.timestamp: datetime = datetime.utcnow()
