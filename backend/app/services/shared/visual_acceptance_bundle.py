"""Compatibility bridge for pack code importing ``services.shared``.

Local-core keeps the concrete implementation at ``app.services``. Capability
source code synced from cloud may import the shared publisher via
``services.shared.visual_acceptance_bundle`` instead, so this module re-exports
the canonical local-core implementation.
"""

from ..visual_acceptance_bundle import *  # noqa: F401,F403
