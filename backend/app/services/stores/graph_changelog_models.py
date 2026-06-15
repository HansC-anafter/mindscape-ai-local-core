import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ChangelogEntry:
    """A single changelog entry"""

    id: str
    workspace_id: str
    version: int
    operation: str
    target_type: str
    target_id: str
    after_state: Dict[str, Any]
    actor: str
    status: str = "pending"
    before_state: Optional[Dict[str, Any]] = None
    actor_context: Optional[str] = None
    created_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    applied_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "version": self.version,
            "operation": self.operation,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "actor": self.actor,
            "actor_context": self.actor_context,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "applied_by": self.applied_by,
        }


def decode_json_state(value: Any, default: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def row_to_changelog_entry(row) -> ChangelogEntry:
    return ChangelogEntry(
        id=row[0],
        workspace_id=row[1],
        version=row[2],
        operation=row[3],
        target_type=row[4],
        target_id=row[5],
        before_state=decode_json_state(row[6]),
        after_state=decode_json_state(row[7], {}) or {},
        actor=row[8],
        actor_context=row[9],
        status=row[10],
        created_at=row[11],
        applied_at=row[12],
        applied_by=row[13],
    )


def rows_to_changelog_entries(rows: Iterable[Any]) -> List[ChangelogEntry]:
    return [row_to_changelog_entry(row) for row in rows]
