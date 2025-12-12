"""
Runtime Factory - Selects appropriate runtime based on execution profile
"""

import logging
from typing import List, Optional

from backend.app.core.runtime_port import RuntimePort, ExecutionProfile

logger = logging.getLogger(__name__)


class RuntimeFactory:
    """Factory to select appropriate runtime based on execution profile"""

    def __init__(self):
        self.runtimes: List[RuntimePort] = []
        self._default_runtime: Optional[RuntimePort] = None

    def register_runtime(self, runtime: RuntimePort, is_default: bool = False):
        """
        Register a runtime provider

        Args:
            runtime: RuntimePort implementation
            is_default: Whether this is the default runtime (fallback)
        """
        if runtime not in self.runtimes:
            self.runtimes.append(runtime)
            if is_default:
                self._default_runtime = runtime
            logger.info(f"Registered runtime: {runtime.name} (default={is_default})")

    def get_runtime(
        self,
        execution_profile: ExecutionProfile
    ) -> RuntimePort:
        """
        Select runtime based on execution profile

        Uses a scoring system to select the best matching runtime:
        1. Checks if runtime supports the profile (supports())
        2. Checks required_capabilities match
        3. Considers side_effect_level requirements
        4. Selects runtime with highest score

        Args:
            execution_profile: ExecutionProfile to match

        Returns:
            RuntimePort that best supports the profile

        Raises:
            RuntimeError: If no runtime is available
        """
        candidates = []

        # Score each runtime
        for runtime in self.runtimes:
            if not runtime.supports(execution_profile):
                continue

            score = 0

            # Base score for supporting the profile
            score += 10

            # Check required_capabilities match
            runtime_caps = set(runtime.capabilities)
            required_caps = set(execution_profile.required_capabilities)
            if required_caps:
                if required_caps.issubset(runtime_caps):
                    score += 20  # All required capabilities available
                else:
                    missing = required_caps - runtime_caps
                    logger.warning(
                        f"Runtime {runtime.name} missing capabilities: {missing}"
                    )
                    continue  # Skip if missing required capabilities

            # Prefer durable runtime for high side effects
            if execution_profile.side_effect_level == "high":
                if execution_profile.execution_mode == "durable":
                    score += 15
                elif execution_profile.execution_mode == "simple":
                    score -= 10  # Penalize simple runtime for high side effects

            # Prefer runtime that supports resume if needed
            if execution_profile.supports_resume:
                if hasattr(runtime, 'supports_resume') and runtime.supports_resume:
                    score += 10

            # Prefer runtime that supports human approval if needed
            if execution_profile.requires_human_approval:
                if hasattr(runtime, 'supports_human_approval') and runtime.supports_human_approval:
                    score += 10

            candidates.append((score, runtime))

        if not candidates:
            # Fallback to default runtime
            if self._default_runtime:
                logger.warning(
                    f"No matching runtime found for profile, using default: {self._default_runtime.name}"
                )
                return self._default_runtime
            raise RuntimeError(
                f"No runtime available for profile: {execution_profile.execution_mode}, "
                f"required_capabilities={execution_profile.required_capabilities}"
            )

        # Select runtime with highest score
        candidates.sort(key=lambda x: x[0], reverse=True)
        selected_runtime = candidates[0][1]
        score = candidates[0][0]

        logger.info(
            f"Selected runtime: {selected_runtime.name} (score={score}) for profile: "
            f"mode={execution_profile.execution_mode}, "
            f"resume={execution_profile.supports_resume}, "
            f"approval={execution_profile.requires_human_approval}, "
            f"side_effect={execution_profile.side_effect_level}, "
            f"capabilities={execution_profile.required_capabilities}"
        )

        return selected_runtime

    def list_runtimes(self) -> List[str]:
        """
        List all registered runtime names

        Returns:
            List of runtime names
        """
        return [r.name for r in self.runtimes]

    def get_default_runtime(self) -> Optional[RuntimePort]:
        """
        Get the default runtime

        Returns:
            Default RuntimePort or None
        """
        return self._default_runtime
