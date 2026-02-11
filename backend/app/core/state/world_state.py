"""
WorldState Schema

Tool results and facts (read-only from tools).
WorldState can only be written by tools, not by LLM or policy.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from enum import Enum


class WorldStateEntryType(str, Enum):
    """WorldState entry type"""
    TOOL_RESULT = "tool_result"
    FACT = "fact"
    OBSERVATION = "observation"


@dataclass
class WorldStateEntry:
    """
    WorldState entry

    Represents a single entry in the WorldState.
    Each entry is immutable once created (can only be appended, not modified).
    """
    entry_id: str
    entry_type: WorldStateEntryType
    source: str  # Source identifier (tool_id, execution_id, etc.)

    # Entry data
    key: str  # Entry key (for lookup)
    value: Any  # Entry value
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "entry_id": self.entry_id,
            "entry_type": self.entry_type.value,
            "source": self.source,
            "key": self.key,
            "value": self.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldStateEntry":
        """Create WorldStateEntry from dictionary"""
        created_at = datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", _utc_now())
        return cls(
            entry_id=data["entry_id"],
            entry_type=WorldStateEntryType(data["entry_type"]),
            source=data["source"],
            key=data["key"],
            value=data["value"],
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )


@dataclass
class WorldState:
    """
    WorldState Schema

    Tool results and facts (read-only from tools).
    WorldState can only be written by tools, not by LLM or policy.

    Write rule: Only tools can write to WorldState.
    """
    # State identification
    state_id: str
    workspace_id: str

    # Entries (immutable, append-only)
    entries: List[WorldStateEntry] = field(default_factory=list)

    # Index for fast lookup
    _key_index: Dict[str, List[WorldStateEntry]] = field(default_factory=dict, init=False)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Version for backward compatibility
    version: str = "1.0"

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize key index"""
        self._rebuild_index()

    def _rebuild_index(self):
        """Rebuild key index"""
        self._key_index = {}
        for entry in self.entries:
            if entry.key not in self._key_index:
                self._key_index[entry.key] = []
            self._key_index[entry.key].append(entry)

    def add_entry(self, entry: WorldStateEntry, source: str) -> None:
        """
        Add entry to WorldState

        Args:
            entry: WorldStateEntry to add
            source: Source identifier (must be a tool_id or execution_id)

        Raises:
            ValueError: If source is not a valid tool source
        """
        # Validate source (must be a tool source)
        if not source.startswith("tool_") and not source.startswith("execution_"):
            raise ValueError(f"WorldState can only be written by tools. Invalid source: {source}")

        self.entries.append(entry)
        self._rebuild_index()
        self.updated_at = _utc_now()

    def get_entry(self, key: str, latest: bool = True) -> Optional[WorldStateEntry]:
        """
        Get entry by key

        Args:
            key: Entry key
            latest: If True, return latest entry; if False, return all entries

        Returns:
            WorldStateEntry or list of WorldStateEntry
        """
        if key not in self._key_index:
            return None

        entries = self._key_index[key]
        if latest:
            return entries[-1] if entries else None
        return entries

    def get_all_entries(self) -> List[WorldStateEntry]:
        """Get all entries"""
        return self.entries.copy()

    def get_entries_by_source(self, source: str) -> List[WorldStateEntry]:
        """Get all entries from a specific source"""
        return [entry for entry in self.entries if entry.source == source]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "version": self.version,
            "state_id": self.state_id,
            "workspace_id": self.workspace_id,
            "entries": [entry.to_dict() for entry in self.entries],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldState":
        """Create WorldState from dictionary"""
        entries = [WorldStateEntry.from_dict(e) for e in data.get("entries", [])]

        created_at = datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", _utc_now())
        updated_at = datetime.fromisoformat(data["updated_at"]) if isinstance(data.get("updated_at"), str) else data.get("updated_at", _utc_now())

        state = cls(
            state_id=data["state_id"],
            workspace_id=data["workspace_id"],
            entries=entries,
            created_at=created_at,
            updated_at=updated_at,
            version=data.get("version", "1.0"),
            metadata=data.get("metadata", {}),
        )
        state._rebuild_index()
        return state










