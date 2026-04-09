"""Input normalization helpers for playbook execution paths."""

from typing import Any, Dict, Optional


def normalize_meeting_session_input_aliases(
    inputs: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Mirror meeting_session_id into legacy session_id when absent.

    Meeting-dispatched playbooks increasingly use ``meeting_session_id`` as the
    canonical field, but older playbook specs and validators still declare
    ``session_id``. This helper keeps both views aligned without overwriting an
    explicit non-empty ``session_id`` provided by the caller.
    """

    normalized_inputs = dict(inputs or {})
    meeting_session_id = normalized_inputs.get("meeting_session_id")
    if not isinstance(meeting_session_id, str):
        return normalized_inputs

    meeting_session_id = meeting_session_id.strip()
    if not meeting_session_id:
        return normalized_inputs

    normalized_inputs["meeting_session_id"] = meeting_session_id

    session_id = normalized_inputs.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        normalized_inputs["session_id"] = meeting_session_id

    return normalized_inputs
