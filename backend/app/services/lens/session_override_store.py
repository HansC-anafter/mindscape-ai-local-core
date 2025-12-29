"""
Session Override Store interface and implementations.

Session Override Store is pluggable to support different storage backends:
- InMemorySessionStore: Default for local-core
- RedisSessionStore: For cloud/multi-worker (future)
- SqliteSessionStore: For persistent local storage (future)
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict
from app.models.graph import LensNodeState


class SessionOverrideStore(ABC):
    """
    Session Override storage abstract interface

    Contract does not bind implementation:
    - Local-core: InMemorySessionStore
    - Cloud/multi-worker: RedisSessionStore / SqliteSessionStore
    """

    @abstractmethod
    def get(self, session_id: str) -> Optional[Dict[str, LensNodeState]]:
        """Get all session overrides"""
        pass

    @abstractmethod
    def set(self, session_id: str, overrides: Dict[str, LensNodeState]) -> None:
        """Set all session overrides (replace existing)"""
        pass

    @abstractmethod
    def update(self, session_id: str, node_id: str, state: LensNodeState) -> None:
        """Update single node override"""
        pass

    @abstractmethod
    def clear(self, session_id: str) -> None:
        """Clear all session overrides"""
        pass


class InMemorySessionStore(SessionOverrideStore):
    """Default implementation for local-core"""
    def __init__(self):
        self._cache: Dict[str, Dict[str, LensNodeState]] = {}

    def get(self, session_id: str) -> Optional[Dict[str, LensNodeState]]:
        """Get all session overrides"""
        return self._cache.get(session_id)

    def set(self, session_id: str, overrides: Dict[str, LensNodeState]) -> None:
        """Set all session overrides (replace existing)"""
        self._cache[session_id] = overrides

    def update(self, session_id: str, node_id: str, state: LensNodeState) -> None:
        """Update single node override"""
        if session_id not in self._cache:
            self._cache[session_id] = {}
        self._cache[session_id][node_id] = state

    def clear(self, session_id: str) -> None:
        """Clear all session overrides"""
        self._cache.pop(session_id, None)

