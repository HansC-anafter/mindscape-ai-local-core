#!/usr/bin/env python3
"""
Content Vault Migration Script

Migrate existing IG post artifacts from database to Content Vault file system.
Preserves original data and marks artifacts as migrated.
"""

import argparse
import sys
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import yaml
import logging

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.models.workspace import Artifact, ArtifactType

logger = logging.getLogger(__name__)


class VaultMigrator:
    """Migrate artifacts to Content Vault"""

    def __init__(self, vault_path: Path, store: MindscapeStore):
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.store = store

    async def migrate_workspace(
        self,
        workspace_id: str,
        series_id: str,
        arc_id: str = "migrated",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Migrate IG posts from a workspace to Content Vault

        Args:
            workspace_id: Workspace ID
            series_id: Series ID for migrated posts
            arc_id: Arc ID for migrated posts (default: "migrated")
            dry_run: If True, only report what would be migrated

        Returns:
            Migration result dictionary
        """
        result = {
            'workspace_id': workspace_id,
            'series_id': series_id,
            'arc_id': arc_id,
            'total_artifacts': 0,
            'migrated_count': 0,
            'failed_count': 0,
            'errors': []
        }

        artifacts = self.store.artifacts.list_artifacts_by_workspace(workspace_id)
        ig_artifacts = [
            a for a in artifacts
            if a.playbook_code == 'ig_post_generation'
            and a.artifact_type == ArtifactType.POST
        ]

        result['total_artifacts'] = len(ig_artifacts)
        logger.info(f"Found {len(ig_artifacts)} IG post artifacts to migrate")

        if dry_run:
            logger.info("DRY RUN: Would migrate the following artifacts:")
            for artifact in ig_artifacts:
                logger.info(f"  - {artifact.id}: {artifact.title}")
            return result

        for artifact in ig_artifacts:
            try:
                posts = self._parse_artifact_content(artifact)
                if not posts:
                    logger.warning(f"Artifact {artifact.id} has no parseable posts")
                    continue

                for post in posts:
                    file_path = self._write_post_to_vault(
                        series_id,
                        arc_id,
                        post,
                        artifact
                    )
                    logger.info(f"Migrated: {file_path}")
                    result['migrated_count'] += 1

                artifact.metadata = artifact.metadata or {}
                artifact.metadata['migrated_to_vault'] = True
                artifact.metadata['vault_file_path'] = str(file_path)
                artifact.metadata['migration_date'] = datetime.now().isoformat()

                self.store.artifacts.update_artifact(
                    artifact.id,
                    metadata=artifact.metadata
                )

            except Exception as e:
                logger.error(f"Failed to migrate artifact {artifact.id}: {e}", exc_info=True)
                result['failed_count'] += 1
                result['errors'].append({
                    'artifact_id': artifact.id,
                    'error': str(e)
                })

        logger.info(f"Migration complete: {result['migrated_count']} posts migrated")
        return result

    def _parse_artifact_content(self, artifact: Artifact) -> List[Dict[str, Any]]:
        """
        Parse artifact content to extract posts

        Args:
            artifact: Artifact object

        Returns:
            List of post dictionaries
        """
        posts = []

        if not artifact.content:
            return posts

        if isinstance(artifact.content, dict):
            if 'ig_posts' in artifact.content:
                posts = artifact.content['ig_posts']
            elif 'posts' in artifact.content:
                posts = artifact.content['posts']
            elif 'text' in artifact.content:
                posts = [{
                    'text': artifact.content.get('text', ''),
                    'hashtags': artifact.content.get('hashtags', []),
                    'narrative_phase': artifact.content.get('narrative_phase', 'unknown'),
                    'emotion': artifact.content.get('emotion', 'neutral')
                }]
        elif isinstance(artifact.content, list):
            posts = artifact.content

        if not isinstance(posts, list):
            return []

        return posts

    def _write_post_to_vault(
        self,
        series_id: str,
        arc_id: str,
        post: Dict[str, Any],
        artifact: Artifact
    ) -> Path:
        """
        Write a single post to vault

        Args:
            series_id: Series ID
            arc_id: Arc ID
            post: Post dictionary
            artifact: Original artifact

        Returns:
            Path to created file
        """
        date_str = artifact.created_at.strftime("%Y-%m-%d") if artifact.created_at else datetime.now().strftime("%Y-%m-%d")
        sequence = self._get_next_sequence(series_id)
        filename = f"{date_str}-{series_id}-{sequence:03d}.md"

        frontmatter = {
            'doc_type': 'post',
            'post_id': f"{series_id}-{sequence:03d}",
            'series_id': series_id,
            'arc_id': arc_id,
            'platform': 'instagram',
            'post_type': 'single_image',
            'sequence': sequence,
            'date': date_str,
            'status': 'published',
            'word_count': len(post.get('text', '')),
            'hashtags_count': len(post.get('hashtags', [])),
            'narrative_phase': post.get('narrative_phase', 'unknown'),
            'emotion': post.get('emotion', 'neutral'),
            'source_artifact_id': artifact.id,
            'source_execution_id': artifact.execution_id,
        }

        if artifact.published_at:
            frontmatter['published_at'] = artifact.published_at.isoformat()

        hashtags_str = ' '.join(['#' + tag for tag in post.get('hashtags', [])]) if post.get('hashtags') else ''

        content = f"""---
{yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False)}---

# Post Content

{post.get('text', '')}

{hashtags_str}

---

## Migration Information

**Original Artifact ID**: {artifact.id}
**Original Execution ID**: {artifact.execution_id}
**Migration Date**: {datetime.now().isoformat()}
"""

        output_path = self.vault_path / "posts" / "instagram" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return output_path

    def _get_next_sequence(self, series_id: str) -> int:
        """Get next sequence number for series"""
        posts_dir = self.vault_path / "posts" / "instagram"
        if not posts_dir.exists():
            return 1

        max_seq = 0
        for md_file in posts_dir.glob(f"*{series_id}*.md"):
            try:
                from backend.app.services.tools.content_vault.vault_tools import parse_frontmatter
                with open(md_file, 'r', encoding='utf-8') as f:
                    frontmatter, _ = parse_frontmatter(f.read())
                seq = frontmatter.get('sequence', 0)
                max_seq = max(max_seq, seq)
            except Exception:
                continue

        return max_seq + 1


async def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(
        description="Migrate IG post artifacts to Content Vault"
    )
    parser.add_argument(
        "--workspace-id",
        type=str,
        help="Workspace ID to migrate"
    )
    parser.add_argument(
        "--all-workspaces",
        action="store_true",
        help="Migrate all workspaces"
    )
    parser.add_argument(
        "--vault-path",
        type=str,
        default=None,
        help="Path to content vault (default: ~/content-vault)"
    )
    parser.add_argument(
        "--series-id",
        type=str,
        required=True,
        help="Series ID for migrated posts"
    )
    parser.add_argument(
        "--arc-id",
        type=str,
        default="migrated",
        help="Arc ID for migrated posts (default: migrated)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (report only, no migration)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if not args.workspace_id and not args.all_workspaces:
        parser.error("Either --workspace-id or --all-workspaces must be specified")

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if args.vault_path:
        vault_path = Path(args.vault_path).expanduser().resolve()
    else:
        import os
        vault_path = Path.home() / "content-vault"

    store = MindscapeStore()
    migrator = VaultMigrator(vault_path, store)

    if args.all_workspaces:
        workspaces = store.workspaces.list_workspaces()
        logger.info(f"Migrating {len(workspaces)} workspaces...")
        for workspace in workspaces:
            result = await migrator.migrate_workspace(
                workspace.id,
                args.series_id,
                args.arc_id,
                args.dry_run
            )
            logger.info(f"Workspace {workspace.id}: {result['migrated_count']} posts migrated")
    else:
        result = await migrator.migrate_workspace(
            args.workspace_id,
            args.series_id,
            args.arc_id,
            args.dry_run
        )
        logger.info(f"Migration result: {result}")

    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())






