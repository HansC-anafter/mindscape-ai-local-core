"""
Playbook File Loader
Loads playbooks from Markdown files with YAML frontmatter
"""

import re
import yaml
import logging
from typing import Dict, Any, Tuple, Optional
from pathlib import Path

from backend.app.models.playbook import Playbook, PlaybookMetadata, PlaybookKind

logger = logging.getLogger(__name__)


class PlaybookFileLoader:
    """Loads playbooks from file system"""

    @staticmethod
    def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
        """
        Parse YAML frontmatter from Markdown content

        Returns:
            (frontmatter_dict, markdown_body)
        """
        # Match YAML frontmatter (between --- markers)
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)

        if not match:
            # No frontmatter, return empty dict and full content as body
            return {}, content

        frontmatter_text = match.group(1)
        markdown_body = match.group(2)

        try:
            frontmatter = yaml.safe_load(frontmatter_text) or {}
            return frontmatter, markdown_body
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse frontmatter: {e}")
            return {}, content

    @staticmethod
    def load_playbook_from_file(file_path: Path) -> Optional[Playbook]:
        """Load a single Playbook from a Markdown file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            frontmatter, sop_content = PlaybookFileLoader.parse_frontmatter(content)

            filename = file_path.stem
            inferred_locale = None
            if filename.endswith('.en'):
                inferred_locale = 'en'
                base_code = filename[:-3]
            else:
                inferred_locale = 'zh-TW'
                base_code = filename

            playbook_code = frontmatter.get('playbook_code')
            if not playbook_code:
                playbook_code = base_code
            else:
                playbook_code = playbook_code.replace('.en', '')

            frontmatter_locale = frontmatter.get('locale')
            if filename.endswith('.en'):
                locale = 'en'
            else:
                locale = frontmatter_locale if frontmatter_locale in ['zh-TW', 'en'] else inferred_locale

            if locale not in ['zh-TW', 'en']:
                logger.warning(f"Unsupported locale {locale} for {playbook_code}, skipping")
                return None

            kind_value = frontmatter.get('kind')
            if kind_value:
                try:
                    kind = PlaybookKind(kind_value)
                except ValueError:
                    kind = PlaybookKind.USER_WORKFLOW
            else:
                kind = PlaybookKind.USER_WORKFLOW

            metadata = PlaybookMetadata(
                playbook_code=playbook_code,
                version=frontmatter.get('version', '1.0.0'),
                locale=locale,
                name=frontmatter.get('name', playbook_code),
                description=frontmatter.get('description', ''),
                tags=frontmatter.get('tags', []),
                kind=kind,
                language_strategy=frontmatter.get('language_strategy', 'model_native'),
                entry_agent_type=frontmatter.get('entry_agent_type'),
                onboarding_task=frontmatter.get('onboarding_task'),
                icon=frontmatter.get('icon'),
                required_tools=frontmatter.get('required_tools', []),
                background=frontmatter.get('background', False),
                optional_tools=frontmatter.get('optional_tools', []),
                scope=frontmatter.get('scope'),
                owner=frontmatter.get('owner'),
                runtime_tier=frontmatter.get('runtime_tier'),
                runtime=frontmatter.get('runtime'),
            )

            playbook = Playbook(
                metadata=metadata,
                sop_content=sop_content.strip()
            )

            return playbook

        except Exception as e:
            logger.error(f"Failed to load playbook from {file_path}: {e}")
            return None

    @staticmethod
    def load_playbook_from_content(
        content: str,
        playbook_code: Optional[str] = None,
        locale: Optional[str] = None
    ) -> Optional[Playbook]:
        """
        Load a Playbook from markdown content string

        Args:
            content: Markdown content with YAML frontmatter
            playbook_code: Optional playbook code (if not in frontmatter)
            locale: Optional locale (if not in frontmatter)

        Returns:
            Playbook instance or None if failed
        """
        try:
            frontmatter, sop_content = PlaybookFileLoader.parse_frontmatter(content)

            # Use provided playbook_code or get from frontmatter
            if not playbook_code:
                playbook_code = frontmatter.get('playbook_code')
                if not playbook_code:
                    logger.warning("No playbook_code provided or found in frontmatter")
                    return None

            # Use provided locale or get from frontmatter
            if not locale:
                locale = frontmatter.get('locale', 'zh-TW')

            if locale not in ['zh-TW', 'en', 'ja']:
                logger.warning(f"Unsupported locale {locale} for {playbook_code}, defaulting to zh-TW")
                locale = 'zh-TW'

            kind_value = frontmatter.get('kind')
            if kind_value:
                try:
                    kind = PlaybookKind(kind_value)
                except ValueError:
                    kind = PlaybookKind.USER_WORKFLOW
            else:
                kind = PlaybookKind.USER_WORKFLOW

            metadata = PlaybookMetadata(
                playbook_code=playbook_code,
                version=frontmatter.get('version', '1.0.0'),
                locale=locale,
                name=frontmatter.get('name', playbook_code),
                description=frontmatter.get('description', ''),
                tags=frontmatter.get('tags', []),
                kind=kind,
                language_strategy=frontmatter.get('language_strategy', 'model_native'),
                entry_agent_type=frontmatter.get('entry_agent_type'),
                onboarding_task=frontmatter.get('onboarding_task'),
                icon=frontmatter.get('icon'),
                required_tools=frontmatter.get('required_tools', []),
                background=frontmatter.get('background', False),
                optional_tools=frontmatter.get('optional_tools', []),
                scope=frontmatter.get('scope'),
                owner=frontmatter.get('owner'),
                runtime_tier=frontmatter.get('runtime_tier'),
                runtime=frontmatter.get('runtime'),
            )

            playbook = Playbook(
                metadata=metadata,
                sop_content=sop_content.strip()
            )

            return playbook

        except Exception as e:
            logger.error(f"Failed to load playbook from content: {e}")
            return None

