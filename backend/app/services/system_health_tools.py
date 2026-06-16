from __future__ import annotations

import logging
from typing import Any, Dict, List

from backend.app.services.system_health_models import HealthIssue, HealthIssueSeverity

logger = logging.getLogger("backend.app.services.system_health_checker")


class SystemHealthToolConnectionMixin:
    async def _check_tool_connections(
        self,
        profile_id: str,
        issues: List[HealthIssue]
    ) -> Dict[str, Dict[str, Any]]:
        """Check tool connections status"""
        tools_status: Dict[str, Dict[str, Any]] = {}

        tool_types_to_check = ["wordpress", "obsidian", "notion", "google_drive"]

        try:
            for tool_type in tool_types_to_check:
                connections = self.tool_registry.get_connections_by_tool_type(
                    profile_id, tool_type
                )
                active_connections = [c for c in connections if c.is_active]

                if active_connections:
                    tools_status[tool_type] = {
                        "connected": True,
                        "status": "ok",
                        "connection_count": len(active_connections)
                    }
                else:
                    tools_status[tool_type] = {
                        "connected": False,
                        "status": "not_configured",
                        "connection_count": 0
                    }

                    if tool_type in ["wordpress", "obsidian", "notion"]:
                        issues.append(HealthIssue(
                            issue_type=f"{tool_type}_not_configured",
                            severity=HealthIssueSeverity.INFO,
                            message=f"{tool_type.capitalize()} is not connected",
                            action_url=f"/settings?tab=tools&tool={tool_type}",
                            tool_type=tool_type
                        ))

        except Exception as e:
            logger.error(f"Failed to check tool connections: {e}", exc_info=True)
            for tool_type in tool_types_to_check:
                tools_status[tool_type] = {
                    "connected": False,
                    "status": "check_failed",
                    "error": str(e)
                }

        return tools_status
