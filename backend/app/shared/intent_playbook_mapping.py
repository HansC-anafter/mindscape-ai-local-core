"""
Intent → Playbook Mapping
Maps intent analysis results to playbook attributes (category/tags) for dynamic query
Uses attribute mapping instead of hardcoded playbook code mapping
"""

import logging
from typing import Dict, List, Optional, Any

from backend.app.services.intent_analyzer import IntentAnalysisResult, TaskDomain
from backend.app.services.playbook_service import PlaybookService
from backend.app.models.playbook import PlaybookMetadata

logger = logging.getLogger(__name__)


# Intent → Playbook attribute mapping
# Maps intent_type/domain → category/tags (NOT direct playbook code)
INTENT_TO_PLAYBOOK_ATTRIBUTES = {
    'artifact_generation': {
        'content': {
            'category': 'content',
            'tags': ['drafting', 'writing', 'content']
        },
        'marketing': {
            'category': 'marketing',
            'tags': ['campaign', 'planning', 'marketing']
        },
        'general': {
            'category': None,  # No specific category
            'tags': ['drafting', 'writing']
        }
    },
    'workflow_execution': {
        'planning': {
            'category': 'planning',
            'tags': ['daily', 'schedule', 'planning']
        },
        'analysis': {
            'category': 'analysis',
            'tags': ['semantic', 'extraction', 'analysis']
        }
    }
}

# TaskDomain → Playbook attribute mapping
# Maps TaskDomain enum values to playbook attributes
TASKDOMAIN_TO_PLAYBOOK_ATTRIBUTES = {
    TaskDomain.PROPOSAL_WRITING: {
        'category': 'proposal',
        'tags': ['proposal', 'writing', 'grant', 'application']
    },
    TaskDomain.YEARLY_REVIEW: {
        'category': 'review',
        'tags': ['yearly', 'review', 'annual', 'book']
    },
    TaskDomain.HABIT_LEARNING: {
        'category': 'habit',
        'tags': ['habit', 'learning', 'organization']
    },
    TaskDomain.PROJECT_PLANNING: {
        'category': 'planning',
        'tags': ['project', 'planning', 'breakdown', 'task']
    },
    TaskDomain.CONTENT_WRITING: {
        'category': 'content',
        'tags': ['content', 'writing', 'drafting', 'copywriting']
    },
    TaskDomain.UNKNOWN: {
        'category': None,
        'tags': []
    }
}


async def select_playbook_for_intent(
    intent_result: IntentAnalysisResult,
    workspace_id: str,
    playbook_service: PlaybookService,
) -> Optional[str]:
    """
    Select most suitable playbook based on intent analysis

    Uses PlaybookService to dynamically query playbooks by attributes (category/tags),
    instead of hardcoded playbook code mapping.

    Args:
        intent_result: IntentAnalysisResult from IntentPipeline.analyze()
        workspace_id: Workspace ID
        playbook_service: PlaybookService instance

    Returns:
        Playbook code if found, None otherwise

    Note:
        - Uses strong typing (IntentAnalysisResult) instead of Dict
        - Uses attribute mapping (category/tags) instead of hardcoded code mapping
        - When IntentAnalysisResult structure changes, IDE will report errors
    """
    # Log intent mapping attempt start
    task_domain_str = intent_result.task_domain.value if intent_result.task_domain else None
    interaction_type_str = intent_result.interaction_type.value if intent_result.interaction_type else None
    logger.info(f"[IntentMapping] Starting playbook selection - workspace_id={workspace_id}, task_domain={task_domain_str}, interaction_type={interaction_type_str}")

    if not intent_result:
        logger.warning("[IntentMapping] FAILED - Intent result is None")
        return None

    # Priority 1: Use selected_playbook_code if already selected by IntentPipeline
    if intent_result.selected_playbook_code:
        logger.info(f"[IntentMapping] SUCCESS (Priority 1: Pre-selected) - Using playbook already selected by IntentPipeline: {intent_result.selected_playbook_code}")
        return intent_result.selected_playbook_code

    # Priority 2: Use task_domain to map to playbook attributes
    if intent_result.task_domain and intent_result.task_domain != TaskDomain.UNKNOWN:
        attributes = TASKDOMAIN_TO_PLAYBOOK_ATTRIBUTES.get(intent_result.task_domain)
        if attributes:
            category = attributes.get('category')
            tags = attributes.get('tags', [])

            logger.info(f"[IntentMapping] Attempting Priority 2 (TaskDomain mapping) - task_domain={intent_result.task_domain.value}, category={category}, tags={tags}")

            # Query playbooks using PlaybookService
            try:
                candidates = await playbook_service.list_playbooks(
                    workspace_id=workspace_id,
                    locale=None,  # Let PlaybookService use default
                    category=category,
                    source=None,  # Get all sources
                    tags=tags if tags else None
                )

                if candidates:
                    # Return first candidate (can be enhanced with scoring later)
                    selected = candidates[0]
                    logger.info(f"[IntentMapping] SUCCESS (Priority 2: TaskDomain mapping) - Selected playbook: {selected.playbook_code} (from {len(candidates)} candidates)")
                    logger.info(f"[IntentMapping] Candidate playbooks: {[c.playbook_code for c in candidates[:5]]}")  # Log first 5 candidates
                    return selected.playbook_code
                else:
                    logger.warning(f"[IntentMapping] FAILED (Priority 2: TaskDomain mapping) - No playbooks found for task_domain={intent_result.task_domain.value}, category={category}, tags={tags}")
            except Exception as e:
                logger.error(f"[IntentMapping] ERROR (Priority 2: TaskDomain mapping) - Exception during playbook query: {e}", exc_info=True)
        else:
            logger.warning(f"[IntentMapping] FAILED (Priority 2: TaskDomain mapping) - No attributes mapping found for task_domain={intent_result.task_domain.value}")

    # Priority 3: Try to infer from interaction_type
    if intent_result.interaction_type:
        # If interaction_type is START_PLAYBOOK, we might need to look at the raw input
        # For now, return None and let the system handle fallback
        logger.info(f"[IntentMapping] Attempting Priority 3 (InteractionType) - interaction_type={intent_result.interaction_type.value}, but no playbook selected")

    logger.warning(f"[IntentMapping] FAILED (All priorities exhausted) - Could not select playbook for intent: task_domain={task_domain_str}, interaction_type={interaction_type_str}")
    return None


def get_playbook_attributes_for_intent(
    intent_type: Optional[str] = None,
    domain: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get playbook attributes (category/tags) for given intent type and domain

    Args:
        intent_type: Intent type (e.g., 'artifact_generation', 'workflow_execution')
        domain: Domain (e.g., 'content', 'marketing', 'planning')

    Returns:
        Dict with 'category' and 'tags' keys
    """
    if intent_type and domain:
        if intent_type in INTENT_TO_PLAYBOOK_ATTRIBUTES:
            domain_mapping = INTENT_TO_PLAYBOOK_ATTRIBUTES[intent_type]
            if domain in domain_mapping:
                return domain_mapping[domain]

    # Fallback: return empty attributes
    return {
        'category': None,
        'tags': []
    }

