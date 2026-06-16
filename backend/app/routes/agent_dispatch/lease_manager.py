"""
Agent Dispatch -- REST lease management mixin facade.

Keeps the public LeaseManagerMixin import path stable for AgentDispatchManager
while the lease responsibilities live in focused mixins.
"""

from .lease_recovery import LeaseRecoveryMixin
from .lease_result_submission import LeaseResultSubmissionMixin
from .lease_state import LeaseStateMixin


class LeaseManagerMixin(
    LeaseRecoveryMixin,
    LeaseStateMixin,
    LeaseResultSubmissionMixin,
):
    """Mixin: REST polling lease management and result submission."""
