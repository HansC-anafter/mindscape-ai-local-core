"""
Workbench lightweight system status helpers.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("backend.app.services.workbench_service")


class WorkbenchStatusMixin:
    """Mixin: lightweight system status projection."""

    async def _get_lightweight_system_status(self, profile_id: str) -> Dict[str, Any]:
        """Get lightweight system status (without full issue details)"""
        try:
            from backend.app.services.system_health_checker import (
                run_readiness_coro_in_worker,
            )

            full_health = await run_readiness_coro_in_worker(
                lambda: self.health_checker.check_workspace_health(
                    profile_id=profile_id
                )
            )

            critical_issues = [
                issue
                for issue in full_health.get("issues", [])
                if issue.get("severity") == "error"
            ]

            return {
                "llm_configured": full_health.get("llm_configured", False),
                "llm_provider": full_health.get("llm_provider"),
                "vector_db_connected": full_health.get("vector_db_connected", False),
                "tools": full_health.get("tools", {}),
                "critical_issues_count": len(critical_issues),
                "has_issues": len(critical_issues) > 0,
            }
        except Exception as e:
            logger.error(f"Failed to get lightweight system status: {e}", exc_info=True)
            return {
                "llm_configured": False,
                "llm_provider": None,
                "vector_db_connected": False,
                "tools": {},
                "critical_issues_count": 1,
                "has_issues": True,
            }
