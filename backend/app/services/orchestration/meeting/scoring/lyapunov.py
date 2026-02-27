"""
L3 Lyapunov V — stability potential function.

V(s) = w_r * risk + w_d * drift - w_p * progress - w_e * evidence

Properties:
- V decreases when the system converges (good)
- V increases when risk/drift rise (warns of instability)
- V is an observation metric, not a hard gate (invariant L3-2)

Weights are tunable; defaults favor risk detection.
"""

import logging
from typing import Optional

from backend.app.models.state_vector import StateVector

logger = logging.getLogger(__name__)

# Default weights: risk and drift push V up; progress and evidence push V down
DEFAULT_WEIGHTS = {
    "w_p": 0.3,  # progress (negative contribution)
    "w_e": 0.2,  # evidence (negative contribution)
    "w_r": 0.3,  # risk (positive contribution)
    "w_d": 0.2,  # drift (positive contribution)
}


def compute_lyapunov_v(
    sv: StateVector,
    weights: Optional[dict] = None,
) -> float:
    """Compute Lyapunov potential V(s) for a state vector.

    V(s) = w_r * risk + w_d * drift - w_p * progress - w_e * evidence

    Returns:
        V value in [-1, 1] range (approximately).
        Lower = more stable/converged.
    """
    w = weights or DEFAULT_WEIGHTS
    v = (
        w["w_r"] * sv.risk
        + w["w_d"] * sv.drift
        - w["w_p"] * sv.progress
        - w["w_e"] * sv.evidence
    )
    return round(v, 6)


def check_descent(
    v_current: float,
    v_previous: float,
) -> bool:
    """Check if V is descending (converging).

    Returns True if the system is moving toward stability.
    """
    return v_current < v_previous


def compute_delta_v(
    v_current: float,
    v_previous: float,
) -> float:
    """Compute the change in V between time steps.

    Negative delta = good (converging).
    Positive delta = bad (diverging).
    """
    return round(v_current - v_previous, 6)
