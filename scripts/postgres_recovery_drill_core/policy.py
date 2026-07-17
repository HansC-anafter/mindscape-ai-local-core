"""Recovery drill scope policy; production resources are never accepted."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DrillScope:
    project: str
    compose_file: Path
    receipt_dir: Path


def validate_drill_scope(scope: DrillScope) -> DrillScope:
    project = scope.project.strip()
    if not project.endswith("-recovery-drill"):
        raise ValueError("drill_project_label_required")
    compose_file = scope.compose_file.resolve()
    if compose_file.name != "docker-compose.yml":
        raise ValueError("root_compose_entrypoint_required")
    receipt_dir = scope.receipt_dir.resolve()
    forbidden = {
        Path("/var/lib/postgresql/data"),
        Path("/app/data"),
        Path.home() / ".mindscape" / "storage",
    }
    if receipt_dir in forbidden:
        raise ValueError("production_path_forbidden")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    return DrillScope(project, compose_file, receipt_dir)
