"""
Feature Flags for Mind-Lens unified implementation.

Controls gradual rollout of new features and system migration.
"""

import os


class FeatureFlags:
    """Feature flags configuration"""

    USE_EFFECTIVE_LENS_RESOLVER: bool = (
        os.getenv("USE_EFFECTIVE_LENS_RESOLVER", "false").lower() == "true"
    )

    # Course production migration: when true, local-core routes are
    # disabled and traffic is handled by the cloud capability.
    COURSE_PRODUCTION_USE_CLOUD: bool = (
        os.getenv("COURSE_PRODUCTION_USE_CLOUD", "false").lower() == "true"
    )
