"""Core helpers for suggestion card creation."""

from backend.app.services.conversation.suggestion_card_creator_core.analysis import (
    extract_playbook_llm_analysis,
    is_background_playbook,
    normalize_llm_analysis,
    prepare_llm_analysis,
)
from backend.app.services.conversation.suggestion_card_creator_core.duplicates import (
    should_create_new_suggestion_task,
)
from backend.app.services.conversation.suggestion_card_creator_core.preferences import (
    check_user_preference,
)
from backend.app.services.conversation.suggestion_card_creator_core.runtime import (
    create_playbook_suggestion,
    create_suggestion_card,
)
from backend.app.services.conversation.suggestion_card_creator_core.task_factory import (
    build_playbook_suggestion_task,
    build_suggestion_task,
    emit_task_created,
)
from backend.app.services.conversation.suggestion_card_creator_core.validation import (
    validate_playbook,
)

__all__ = [
    "build_playbook_suggestion_task",
    "build_suggestion_task",
    "check_user_preference",
    "create_playbook_suggestion",
    "create_suggestion_card",
    "emit_task_created",
    "extract_playbook_llm_analysis",
    "is_background_playbook",
    "normalize_llm_analysis",
    "prepare_llm_analysis",
    "should_create_new_suggestion_task",
    "validate_playbook",
]
