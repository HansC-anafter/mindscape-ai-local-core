"""
Runtime Degradation Registry

Tracks capability runtime degradation status.

When optional dependencies are unavailable, capabilities can run in degraded
mode with only a subset of features enabled.
"""

from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
import logging
import threading

logger = logging.getLogger(__name__)


@dataclass
class CapabilityStatus:
    """Capability runtime status."""
    code: str
    status: str  # "healthy" | "degraded" | "unavailable"
    available_features: List[str] = field(default_factory=list)
    degraded_features: List[str] = field(default_factory=list)
    unavailable_features: List[str] = field(default_factory=list)
    missing_dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert the status to a dictionary."""
        return {
            "code": self.code,
            "status": self.status,
            "available_features": self.available_features,
            "degraded_features": self.degraded_features,
            "unavailable_features": self.unavailable_features,
            "missing_dependencies": self.missing_dependencies,
        }


class DegradationRegistry:
    """
    Global degradation status registry.

    Uses a singleton so runtime status is shared process-wide.

    Example:
        registry = DegradationRegistry()

        registry.register_capability(
            code="example_pack",
            all_features=["pipeline", "qa", "export"],
            missing_deps=["optional_provider"],
            degraded_features_map={
                "optional_provider": ["export"]
            }
        )

        if registry.is_feature_available("example_pack", "pipeline"):
            run_pipeline()
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._capabilities: Dict[str, CapabilityStatus] = {}
                    cls._instance._initialized = True
        return cls._instance

    def register_capability(
        self,
        code: str,
        all_features: List[str],
        missing_deps: List[str],
        degraded_features_map: Dict[str, List[str]]
    ) -> CapabilityStatus:
        """
        Register capability status.

        Args:
            code: Capability code.
            all_features: Full feature list.
            missing_deps: Missing dependency list.
            degraded_features_map: Dependency to degraded feature mapping.

        Returns:
            CapabilityStatus.
        """
        degraded_features: Set[str] = set()
        for dep in missing_deps:
            features = degraded_features_map.get(dep, [])
            degraded_features.update(features)

        available = [f for f in all_features if f not in degraded_features]

        if len(degraded_features) == 0:
            status = "healthy"
        elif len(degraded_features) == len(all_features):
            status = "unavailable"
        else:
            status = "degraded"

        cap_status = CapabilityStatus(
            code=code,
            status=status,
            available_features=available,
            degraded_features=list(degraded_features),
            missing_dependencies=missing_deps
        )

        self._capabilities[code] = cap_status

        if status == "degraded":
            logger.warning(
                f"Capability '{code}' running in degraded mode. "
                f"Degraded features: {list(degraded_features)}. "
                f"Missing dependencies: {missing_deps}"
            )
        elif status == "unavailable":
            logger.error(
                f"Capability '{code}' is unavailable. "
                f"Missing dependencies: {missing_deps}"
            )
        else:
            logger.info(f"Capability '{code}' registered as healthy")

        return cap_status

    def get_status(self, code: str) -> Optional[CapabilityStatus]:
        """
        Get capability status.

        Args:
            code: Capability code.

        Returns:
            CapabilityStatus or None.
        """
        return self._capabilities.get(code)

    def get_all_statuses(self) -> Dict[str, CapabilityStatus]:
        """Get all capability statuses."""
        return self._capabilities.copy()

    def is_feature_available(self, capability_code: str, feature: str) -> bool:
        """
        Check whether a feature is available.

        Args:
            capability_code: Capability code.
            feature: Feature name.

        Returns:
            True if the feature is available.
        """
        status = self._capabilities.get(capability_code)
        if not status:
            return True
        return feature in status.available_features

    def is_capability_healthy(self, code: str) -> bool:
        """
        Check whether a capability is healthy.

        Args:
            code: Capability code.

        Returns:
            True if healthy.
        """
        status = self._capabilities.get(code)
        if not status:
            return True
        return status.status == "healthy"

    def is_capability_available(self, code: str) -> bool:
        """
        Check whether a capability is available, including degraded mode.

        Args:
            code: Capability code

        Returns:
            True if available.
        """
        status = self._capabilities.get(code)
        if not status:
            return True
        return status.status in ("healthy", "degraded")

    def clear(self):
        """Clear all statuses. Primarily used by tests."""
        self._capabilities.clear()


def get_capability_status(code: str) -> Optional[CapabilityStatus]:
    """Get capability status."""
    return DegradationRegistry().get_status(code)


def is_feature_available(capability_code: str, feature: str) -> bool:
    """Check whether a feature is available."""
    return DegradationRegistry().is_feature_available(capability_code, feature)

