"""Scans capabilities for migration metadata."""

import logging
import yaml
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class MigrationMetadata:
    """Represents migration metadata for a capability."""

    def __init__(self, capability_code: str, db_type: str, revisions: List[str],
                 depends_on: List[str] = None, migration_paths: List[str] = None):
        self.capability_code = capability_code
        self.db_type = db_type
        self.revisions = revisions
        self.depends_on = depends_on or []
        self.migration_paths = migration_paths or []


class MigrationScanner:
    """Scans capabilities directory for migration metadata."""

    def __init__(self, capabilities_root: Path):
        self.capabilities_root = capabilities_root

    def scan_capabilities(self) -> List[MigrationMetadata]:
        """Scan all capabilities for migrations.yaml files."""
        metadata_list = []

        for capability_dir in self.capabilities_root.iterdir():
            if not capability_dir.is_dir():
                continue

            migrations_yaml = capability_dir / "migrations.yaml"
            if not migrations_yaml.exists():
                continue

            try:
                with open(migrations_yaml, 'r') as f:
                    data = yaml.safe_load(f)

                metadata = MigrationMetadata(
                    capability_code=capability_dir.name,
                    db_type=data['db'],
                    revisions=data.get('revisions', []),
                    depends_on=data.get('depends_on', []),
                    migration_paths=data.get('migration_paths', [])
                )
                metadata_list.append(metadata)
                logger.info(f"Found migrations for {capability_dir.name}: {len(metadata.revisions)} revisions")
            except Exception as e:
                logger.error(f"Failed to parse migrations.yaml for {capability_dir.name}: {e}")

        return metadata_list

    def find_migration_files(self, metadata: MigrationMetadata) -> List[Path]:
        """Find actual migration files for a capability."""
        migration_files = []
        capability_dir = self.capabilities_root / metadata.capability_code

        # Check custom paths first
        if metadata.migration_paths:
            for rel_path in metadata.migration_paths:
                full_path = capability_dir / rel_path
                if full_path.exists():
                    migration_files.extend(full_path.glob("*.py"))
        else:
            # Default: look in standard Alembic locations
            # This will be handled by Alembic's version_locations
            pass

        return migration_files

