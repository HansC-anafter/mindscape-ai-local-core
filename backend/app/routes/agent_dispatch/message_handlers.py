"""
Agent Dispatch -- WS message handlers mixin.

Handles incoming messages from IDE clients: ack, progress, result,
ownership verification, and result landing to workspace filesystem.
"""

from .message_completion_state import MessageCompletionStateMixin
from .message_ingress_handlers import MessageIngressHandlersMixin
from .message_result_finalization import MessageResultFinalizationMixin


class MessageHandlersMixin(
    MessageIngressHandlersMixin,
    MessageResultFinalizationMixin,
    MessageCompletionStateMixin,
):
    """Mixin: incoming WS message routing and result handling."""
