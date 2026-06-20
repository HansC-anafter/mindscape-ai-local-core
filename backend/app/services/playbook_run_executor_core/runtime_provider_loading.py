"""Runtime provider loading helpers for PlaybookRunExecutor."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def load_runtime_providers(runtime_factory: Any) -> None:
    """Load runtime providers from installed capability packs."""
    try:
        from backend.app.services.runtime.capability_runtime_loader import (
            CapabilityRuntimeLoader,
        )

        loader = CapabilityRuntimeLoader()
        loaded_runtimes = loader.load_all_runtime_providers()

        for runtime in loaded_runtimes:
            runtime_factory.register_runtime(runtime)
            logger.info("Registered runtime provider: %s", runtime.name)

        if loaded_runtimes:
            logger.info(
                "Loaded %d runtime provider(s) from capability packs",
                len(loaded_runtimes),
            )
        else:
            logger.debug("No runtime providers found in capability packs")

    except Exception as exc:
        logger.warning("Failed to load runtime providers: %s", exc, exc_info=True)
