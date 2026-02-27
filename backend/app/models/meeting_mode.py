"""
L3 MeetingMode FSM — four-mode finite state machine for meeting convergence.

Modes:
    EXPLORE  — gathering information, broad discussion
    CONVERGE — narrowing down, building consensus
    DELIVER  — finalizing decisions, creating action items
    DEBUG    — risk detected, investigating issues

Transitions are evaluated against StateVector thresholds.
"""

from enum import Enum
from typing import Callable, Dict, Optional, Tuple

from backend.app.models.state_vector import StateVector


class MeetingMode(str, Enum):
    """Meeting convergence mode."""

    EXPLORE = "explore"
    CONVERGE = "converge"
    DELIVER = "deliver"
    DEBUG = "debug"


# Transition guard functions: (from, to) -> condition(StateVector) -> bool
MODE_TRANSITIONS: Dict[
    Tuple[MeetingMode, MeetingMode], Callable[[StateVector], bool]
] = {
    (MeetingMode.EXPLORE, MeetingMode.CONVERGE): (
        lambda sv: sv.evidence >= 0.5 and sv.progress >= 0.3
    ),
    (MeetingMode.CONVERGE, MeetingMode.DELIVER): (
        lambda sv: sv.progress >= 0.7 and sv.risk <= 0.3
    ),
    (MeetingMode.DELIVER, MeetingMode.CONVERGE): (lambda sv: sv.progress < 0.5),
}


def can_enter_debug(sv: StateVector) -> bool:
    """Any mode can transition to DEBUG when risk is high."""
    return sv.risk >= 0.7


def can_exit_debug(sv: StateVector) -> bool:
    """DEBUG exits back to previous mode when risk drops."""
    return sv.risk < 0.5


def evaluate_transition(
    current_mode: MeetingMode,
    sv: StateVector,
    previous_mode: Optional[MeetingMode] = None,
) -> Optional[MeetingMode]:
    """Evaluate whether a mode transition should occur.

    Args:
        current_mode: Current meeting mode.
        sv: Current state vector.
        previous_mode: Mode before entering DEBUG (for exit routing).

    Returns:
        New mode if transition should occur, None otherwise.
    """
    # Debug entry: any mode -> DEBUG
    if current_mode != MeetingMode.DEBUG and can_enter_debug(sv):
        return MeetingMode.DEBUG

    # Debug exit: return to previous mode
    if current_mode == MeetingMode.DEBUG and can_exit_debug(sv):
        return previous_mode or MeetingMode.EXPLORE

    # Normal transitions
    for (from_mode, to_mode), guard in MODE_TRANSITIONS.items():
        if current_mode == from_mode and guard(sv):
            return to_mode

    return None
