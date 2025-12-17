"""
Service interfaces for web generation capability.

Enables cloud capability APIs to depend on abstractions
rather than concrete implementations for better separation of concerns.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class IBaselineService(ABC):
    """Interface for baseline management service"""

    @abstractmethod
    def get_baseline(self, workspace_id: str, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get baseline configuration for workspace/project"""
        pass

    @abstractmethod
    def create_or_update_baseline(
        self,
        workspace_id: str,
        snapshot_id: str,
        variant_id: Optional[str] = None,
        project_id: Optional[str] = None,
        lock_mode: str = "advisory",
        bound_spec_version: Optional[str] = None,
        bound_outline_version: Optional[str] = None,
        updated_by: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create or update baseline configuration"""
        pass

    @abstractmethod
    def check_baseline_stale(
        self,
        baseline: Dict[str, Any],
        current_spec_version: Optional[str],
        current_outline_version: Optional[str]
    ) -> Dict[str, Any]:
        """Check if baseline is stale compared to current versions"""
        pass

    @abstractmethod
    def record_baseline_event(
        self,
        event_type: str,
        workspace_id: str,
        snapshot_id: str,
        new_state: Dict[str, Any],
        triggered_by: str,
        project_id: Optional[str] = None,
        variant_id: Optional[str] = None,
        previous_state: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None
    ) -> str:
        """Record a baseline governance event"""
        pass

    @abstractmethod
    def list_baseline_events(
        self,
        workspace_id: str,
        project_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List baseline events for workspace/project"""
        pass


class IMindscapeStore(ABC):
    """Interface for artifact store (simplified for web generation use)"""

    @property
    @abstractmethod
    def artifacts(self) -> Any:
        """Get artifacts store interface"""
        pass
