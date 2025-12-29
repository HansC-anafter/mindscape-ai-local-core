"""
Feature Flags for Mind-Lens unified implementation.

Controls gradual rollout of new features and system migration.
"""
import os


class FeatureFlags:
    """Feature flags configuration"""

    USE_EFFECTIVE_LENS_RESOLVER: bool = os.getenv(
        "USE_EFFECTIVE_LENS_RESOLVER",
        "false"
    ).lower() == "true"

