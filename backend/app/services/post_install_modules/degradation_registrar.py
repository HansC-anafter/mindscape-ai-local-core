"""
Degradation Registrar

Registers capability degradation status.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class DegradationRegistrar:
    """Registers capability degradation status"""

    def register_degradation_status(
        self,
        capability_code: str,
        manifest: Dict,
        missing_required: List[str],
        missing_optional: List[str],
        degraded_features_map: Dict[str, List[str]],
        result
    ):
        """
        Register capability degradation status

        Args:
            capability_code: Capability code
            manifest: Parsed manifest dictionary
            missing_required: List of missing required dependencies
            missing_optional: List of missing optional dependencies
            degraded_features_map: Map of dependency -> degraded features
            result: InstallResult object
        """
        try:
            from mindscape.runtime.degradation import DegradationRegistry

            # Collect all features from manifest
            all_features = []

            # Features from playbooks
            playbooks = manifest.get('playbooks', [])
            for pb in playbooks:
                pb_code = pb.get('code', '')
                if pb_code:
                    all_features.append(pb_code)

            # Features from tools
            tools = manifest.get('tools', [])
            for tool in tools:
                tool_name = tool.get('name', '')
                if tool_name:
                    all_features.append(tool_name)

            # Register with degradation registry
            registry = DegradationRegistry()
            cap_status = registry.register_capability(
                code=capability_code,
                all_features=all_features,
                missing_deps=missing_required + missing_optional,
                degraded_features_map=degraded_features_map
            )

            # Add to result
            result.degradation_status = cap_status.to_dict()
            logger.info(
                f"Registered degradation status for {capability_code}: "
                f"status={cap_status.status}, "
                f"degraded_features={cap_status.degraded_features}"
            )

        except ImportError:
            logger.warning("DegradationRegistry not available, skipping degradation registration")
            result.add_warning("Degradation status not registered (DegradationRegistry not available)")
        except Exception as e:
            logger.warning(f"Failed to register degradation status: {e}")
            result.add_warning(f"Failed to register degradation status: {e}")

