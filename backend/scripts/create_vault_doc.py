#!/usr/bin/env python3
"""
Content Vault Document Creator

Generate Content Vault documents (Series, Arc, Post) from templates.
Automatically validates generated documents.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import yaml
import logging

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from backend.scripts.validate_vault import VaultValidator

logger = logging.getLogger(__name__)


class VaultDocCreator:
    """Create Content Vault documents from templates"""

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.templates_dir = self.vault_path / "assets" / "templates"

    def create_series(
        self,
        series_id: str,
        title: str,
        platform: str = "instagram",
        theme: Optional[str] = None,
        tone: Optional[str] = None,
        target_audience: Optional[str] = None,
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Create a Series document

        Args:
            series_id: Series identifier
            title: Series title
            platform: Platform (default: instagram)
            theme: Theme description
            tone: Tone description
            target_audience: Target audience description
            output_path: Output file path (default: vault_path/series/{series_id}.md)

        Returns:
            Path to created file
        """
        if output_path is None:
            output_path = self.vault_path / "series" / f"{series_id}.md"

        frontmatter = {
            'doc_type': 'series',
            'series_id': series_id,
            'title': title,
            'platform': platform,
            'status': 'active',
            'created_at': datetime.now().strftime('%Y-%m-%d')
        }

        if theme:
            frontmatter['theme'] = theme
        if tone:
            frontmatter['tone'] = tone
        if target_audience:
            frontmatter['target_audience'] = target_audience

        content = self._build_document(frontmatter, f"# {title}\n\n## Series Introduction\n\n(Describe the core concept and goals)\n\n## Narrative Strategy\n\n1.\n2.\n\n## Future Direction\n\n-")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"Created Series document: {output_path}")
        return output_path

    def create_arc(
        self,
        arc_id: str,
        series_id: str,
        title: str,
        start_date: str,
        end_date: str,
        arc_theme: Optional[str] = None,
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Create an Arc document

        Args:
            arc_id: Arc identifier
            series_id: Series identifier
            title: Arc title
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            arc_theme: Arc theme description
            output_path: Output file path (default: vault_path/arcs/{arc_id}.md)

        Returns:
            Path to created file
        """
        if output_path is None:
            output_path = self.vault_path / "arcs" / f"{arc_id}.md"

        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        duration_weeks = (end_dt - start_dt).days // 7

        frontmatter = {
            'doc_type': 'arc',
            'arc_id': arc_id,
            'series_id': series_id,
            'title': title,
            'start_date': start_date,
            'end_date': end_date,
            'duration_weeks': duration_weeks,
            'status': 'planning'
        }

        if arc_theme:
            frontmatter['arc_theme'] = arc_theme

        content = self._build_document(frontmatter, f"# {title}\n\n## Arc Background\n\n(Why design this arc?)\n\n## Narrative Rhythm\n\nWeek 1:\n-\n\nWeek 2:\n-\n\n## Published Posts\n\n(Will be updated automatically)\n\n## Pending Topics\n\n- [ ]")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"Created Arc document: {output_path}")
        return output_path

    def create_post(
        self,
        post_id: str,
        series_id: str,
        platform: str = "instagram",
        sequence: Optional[int] = None,
        arc_id: Optional[str] = None,
        date: Optional[str] = None,
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Create a Post document

        Args:
            post_id: Post identifier
            series_id: Series identifier
            platform: Platform (default: instagram)
            sequence: Sequence number (auto-incremented if not provided)
            arc_id: Arc identifier (optional)
            date: Post date (YYYY-MM-DD, default: today)
            output_path: Output file path (default: vault_path/posts/{platform}/{date}-{series_id}-{sequence:03d}.md)

        Returns:
            Path to created file
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        if sequence is None:
            sequence = self._get_next_sequence(series_id, platform)

        if output_path is None:
            filename = f"{date}-{series_id}-{sequence:03d}.md"
            output_path = self.vault_path / "posts" / platform / filename

        frontmatter = {
            'doc_type': 'post',
            'post_id': post_id,
            'series_id': series_id,
            'platform': platform,
            'post_type': 'single_image',
            'sequence': sequence,
            'date': date,
            'status': 'draft'
        }

        if arc_id:
            frontmatter['arc_id'] = arc_id

        content = self._build_document(frontmatter, "# Post Content\n\n(Write post content here)\n\n(Hashtags)\n\n---\n\n## Creation Notes\n\n**Inspiration Source**:\n\n**Narrative Techniques**:\n\n**Arc Connection**:")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"Created Post document: {output_path}")
        return output_path

    def _get_next_sequence(self, series_id: str, platform: str) -> int:
        """Get next sequence number for series"""
        posts_dir = self.vault_path / "posts" / platform
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

    def _build_document(self, frontmatter: Dict[str, Any], body: str) -> str:
        """Build complete Markdown document with frontmatter"""
        fm_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return f"---\n{fm_yaml}---\n\n{body}\n"


def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(
        description="Create Content Vault documents from templates"
    )
    parser.add_argument(
        "--vault-path",
        type=str,
        default=None,
        help="Path to content vault (default: ~/content-vault)"
    )
    parser.add_argument(
        "--type",
        type=str,
        required=True,
        choices=['series', 'arc', 'post'],
        help="Document type"
    )
    parser.add_argument(
        "--id",
        type=str,
        required=True,
        help="Document identifier (series_id, arc_id, or post_id)"
    )
    parser.add_argument(
        "--title",
        type=str,
        help="Document title (required for series and arc)"
    )
    parser.add_argument(
        "--series-id",
        type=str,
        help="Series ID (required for arc and post)"
    )
    parser.add_argument(
        "--platform",
        type=str,
        default="instagram",
        help="Platform (default: instagram)"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date for arc (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date for arc (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--arc-id",
        type=str,
        help="Arc ID (optional for post)"
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Post date (YYYY-MM-DD, default: today)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (optional)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate created document"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

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

    creator = VaultDocCreator(vault_path)

    try:
        if args.type == 'series':
            if not args.title:
                parser.error("--title is required for series")
            output_path = creator.create_series(
                series_id=args.id,
                title=args.title,
                platform=args.platform,
                output_path=Path(args.output) if args.output else None
            )
        elif args.type == 'arc':
            if not args.title:
                parser.error("--title is required for arc")
            if not args.series_id:
                parser.error("--series-id is required for arc")
            if not args.start_date or not args.end_date:
                parser.error("--start-date and --end-date are required for arc")
            output_path = creator.create_arc(
                arc_id=args.id,
                series_id=args.series_id,
                title=args.title,
                start_date=args.start_date,
                end_date=args.end_date,
                output_path=Path(args.output) if args.output else None
            )
        elif args.type == 'post':
            if not args.series_id:
                parser.error("--series-id is required for post")
            output_path = creator.create_post(
                post_id=args.id,
                series_id=args.series_id,
                platform=args.platform,
                arc_id=args.arc_id,
                date=args.date,
                output_path=Path(args.output) if args.output else None
            )

        print(f"Created {args.type} document: {output_path}")

        if args.validate:
            validator = VaultValidator(vault_path)
            is_valid, errors, warnings = validator.validate_vault()
            if is_valid:
                print("Document validation passed")
            else:
                print(f"ERROR: Validation found {len(errors)} error(s)")
                for error in errors:
                    if str(output_path) in error['file']:
                        print(f"  - {error['message']}")

    except Exception as e:
        logger.error(f"Failed to create document: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

