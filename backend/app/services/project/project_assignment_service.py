"""
Project Assignment Service

Central service for assigning projects to user messages.
Coordinates between ProjectIndex, ProjectAssignmentAgent, and conversation context.
"""

import logging
from typing import Dict, Any, Optional
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_index import ProjectIndex
from backend.app.services.project.project_assignment_agent import ProjectAssignmentAgent
from backend.app.services.project.project_manager import ProjectManager

logger = logging.getLogger(__name__)
stats_logger = logging.getLogger(f"{__name__}.stats")

# Statistics logger - separate logger for statistics to allow filtering
stats_logger = logging.getLogger(f"{__name__}.stats")


class ProjectAssignmentResult:
    """
    Result of project assignment

    This class represents a SUGGESTION, not a final decision.
    The frontend decides whether to adopt it based on project_assignment_mode + confidence.
    """
    def __init__(
        self,
        project_id: Optional[str],
        phase_id: Optional[str],
        relation: str,
        confidence: float,
        reasoning: str,
        candidates: list,
        assignment_mode: Optional[str] = None
    ):
        self.project_id = project_id
        self.phase_id = phase_id
        self.relation = relation
        self.confidence = confidence
        self.reasoning = reasoning
        self.candidates = candidates

        # Calculate requires_ui_confirmation based on mode + confidence
        self.requires_ui_confirmation = False
        if assignment_mode:
            self.requires_ui_confirmation = self.should_require_ui_confirmation(assignment_mode)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dict for frontend

        Note: This is a SUGGESTION. Frontend decides final adoption based on mode + confidence.
        """
        # Extract project title from first candidate if available
        project_title = None
        if self.candidates and len(self.candidates) > 0:
            first_candidate = self.candidates[0]
            project_obj = first_candidate.get("project")
            if project_obj:
                if hasattr(project_obj, "title"):
                    project_title = project_obj.title
                elif isinstance(project_obj, dict):
                    project_title = project_obj.get("title")

        return {
            "project_id": self.project_id,
            "phase_id": self.phase_id,
            "project_title": project_title,
            "relation": self.relation,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "requires_ui_confirmation": self.requires_ui_confirmation,
            "candidates": [
                {
                    "project_id": c.get("project_id"),
                    "project": c.get("project").dict() if hasattr(c.get("project"), "dict") else c.get("project"),
                    "similarity": c.get("similarity", 0.0)
                }
                for c in self.candidates
            ]
        }

    def should_require_ui_confirmation(
        self,
        assignment_mode: str
    ) -> bool:
        """
        Determine if UI confirmation is needed based on mode and confidence

        Args:
            assignment_mode: Project assignment mode (auto_silent | assistive | manual_first)

        Returns:
            True if UI confirmation is required
        """
        if assignment_mode == "manual_first":
            return True

        if assignment_mode == "assistive":
            return self.confidence < 0.8

        if assignment_mode == "auto_silent":
            return False

        return False


class ProjectAssignmentService:
    """
    Project Assignment Service - assigns projects to user messages

    Decision order:
    1. UI explicitly selected project
    2. Conversation-level binding (primary_project_id)
    3. LLM judgment (ProjectAssignmentAgent)
    """

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.project_index = ProjectIndex(store)
        self.project_assignment_agent = ProjectAssignmentAgent()
        self.project_manager = ProjectManager(store)

        # Statistics counters
        self._stats = {
            "relation_counts": {
                "same_project": 0,
                "new_project": 0,
                "ambiguous": 0
            },
            "confidence_buckets": {
                "low": 0,      # < 0.5
                "medium": 0,   # 0.5 - 0.8
                "high": 0      # >= 0.8
            },
            "ui_overrides": 0,
            "total_assignments": 0
        }

    async def assign_project(
        self,
        message: str,
        workspace_id: str,
        message_id: str,
        conversation_id: Optional[str] = None,
        ui_selected_project_id: Optional[str] = None
    ) -> ProjectAssignmentResult:
        """
        Assign project for a message

        Args:
            message: User message
            workspace_id: Workspace ID
            message_id: Message ID
            conversation_id: Conversation ID (for tracking conversation-level binding)
            ui_selected_project_id: UI explicitly selected project ID

        Returns:
            ProjectAssignmentResult
        """
        # Get workspace to determine assignment mode
        workspace = self.store.get_workspace(workspace_id)
        assignment_mode = "auto_silent"
        if workspace:
            assignment_mode_enum = getattr(workspace, "project_assignment_mode", None)
            if assignment_mode_enum:
                if hasattr(assignment_mode_enum, "value"):
                    assignment_mode = assignment_mode_enum.value
                else:
                    assignment_mode = str(assignment_mode_enum)

        # Decision 1: UI explicitly selected project
        if ui_selected_project_id:
            self._stats["ui_overrides"] += 1
            self._stats["total_assignments"] += 1
            self._stats["relation_counts"]["same_project"] += 1
            self._stats["confidence_buckets"]["high"] += 1

            logger.info(f"Using UI selected project: {ui_selected_project_id}")
            result = ProjectAssignmentResult(
                project_id=ui_selected_project_id,
                phase_id=None,
                relation="same_project",
                confidence=1.0,
                reasoning="User explicitly selected this project in UI",
                candidates=[],
                assignment_mode=assignment_mode
            )
            self._log_statistics()
            return result

        # Decision 2: Conversation-level binding
        last_project_id = await self._get_conversation_primary_project(conversation_id)
        if last_project_id:
            # Check if project still exists and is active
            project = await self.project_manager.get_project(last_project_id, workspace_id=workspace_id)
            if project and project.state == "open":
                logger.info(f"Using conversation-level bound project: {last_project_id}")
                # Still run LLM to check if user wants to switch, but bias towards same project
                pass

        # Decision 3: LLM judgment with ProjectIndex retrieval
        # Get candidate projects using vector search
        candidates = await self.project_index.top_k_similar(
            workspace_id=workspace_id,
            text=message,
            k=3
        )

        # Get conversation context if available
        conversation_context = await self._get_conversation_context(conversation_id)

        # Call ProjectAssignmentAgent
        decision = await self.project_assignment_agent.assign_project_for_message(
            message=message,
            workspace_id=workspace_id,
            project_candidates=candidates,
            last_project_id=last_project_id,
            conversation_context=conversation_context
        )

        # Create result (this is a SUGGESTION, not a final decision)
        result = ProjectAssignmentResult(
            project_id=decision.get("project_id"),
            phase_id=None,
            relation=decision.get("relation", "ambiguous"),
            confidence=decision.get("confidence", 0.0),
            reasoning=decision.get("reasoning", ""),
            candidates=candidates,
            assignment_mode=assignment_mode
        )

        # Update conversation-level binding if confidence is high
        if decision.get("relation") == "same_project" and decision.get("confidence", 0.0) >= 0.8:
            await self._set_conversation_primary_project(
                conversation_id,
                decision.get("project_id")
            )

        # Update statistics
        self._update_statistics(result.relation, result.confidence)

        logger.info(
            f"Project assignment result: project_id={result.project_id}, "
            f"relation={result.relation}, confidence={result.confidence:.2f}"
        )

        return result

    async def _get_conversation_primary_project(
        self,
        conversation_id: Optional[str]
    ) -> Optional[str]:
        """
        Get conversation-level primary project ID

        Args:
            conversation_id: Conversation ID

        Returns:
            Primary project ID or None

        NOTE: Currently not implemented. System relies on UI selection and LLM-based assignment.
        """
        # TODO: Implement conversation store lookup
        # For now, return None
        return None

    async def _set_conversation_primary_project(
        self,
        conversation_id: Optional[str],
        project_id: Optional[str]
    ) -> None:
        """
        Set conversation-level primary project ID

        Args:
            conversation_id: Conversation ID
            project_id: Project ID to set

        NOTE: Currently not implemented.
        """
        pass

    async def _get_conversation_context(
        self,
        conversation_id: Optional[str]
    ) -> Optional[list]:
        """
        Get recent conversation context

        Args:
            conversation_id: Conversation ID

        Returns:
            List of {role, content} messages or None

        NOTE: Currently not implemented. Conversation context is not used in assignment decisions.
        """
        # TODO: Implement conversation context retrieval
        # For now, return None
        return None

    def _update_statistics(self, relation: str, confidence: float) -> None:
        """
        Update statistics counters

        Args:
            relation: Assignment relation (same_project, new_project, ambiguous)
            confidence: Confidence score (0.0 - 1.0)
        """
        self._stats["total_assignments"] += 1

        # Update relation counts
        if relation in self._stats["relation_counts"]:
            self._stats["relation_counts"][relation] += 1

        # Update confidence buckets
        if confidence < 0.5:
            self._stats["confidence_buckets"]["low"] += 1
        elif confidence < 0.8:
            self._stats["confidence_buckets"]["medium"] += 1
        else:
            self._stats["confidence_buckets"]["high"] += 1

        # Log statistics periodically (every 10 assignments) or on significant events
        if self._stats["total_assignments"] % 10 == 0:
            self._log_statistics()

    def _log_statistics(self) -> None:
        """
        Log statistics summary
        """
        total = self._stats["total_assignments"]
        if total == 0:
            return

        rel_counts = self._stats["relation_counts"]
        conf_buckets = self._stats["confidence_buckets"]

        stats_logger.info(
            f"ProjectAssignment statistics (total={total}): "
            f"relations[same={rel_counts['same_project']}, new={rel_counts['new_project']}, ambiguous={rel_counts['ambiguous']}], "
            f"confidence[low={conf_buckets['low']}, medium={conf_buckets['medium']}, high={conf_buckets['high']}], "
            f"ui_overrides={self._stats['ui_overrides']}"
        )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get current statistics

        Returns:
            Statistics dictionary
        """
        return self._stats.copy()

