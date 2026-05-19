"""
CTA Handler

Public facade for CTA actions from timeline items.
"""

from .cta_handler_core import (
    CTAConfirmationMixin,
    CTAExternalWriteMixin,
    CTAHandlerBase,
    CTAOrchestratorMixin,
    CTASoftWriteMixin,
    _utc_now,
)


class CTAHandler(
    CTAOrchestratorMixin,
    CTASoftWriteMixin,
    CTAExternalWriteMixin,
    CTAConfirmationMixin,
    CTAHandlerBase,
):
    """
    Handles CTA actions from timeline items.

    Supports:
    - soft_write actions.
    - external_write actions.
    """


__all__ = ["CTAHandler", "_utc_now"]
