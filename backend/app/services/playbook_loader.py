"""
Playbook Loader
Load Playbooks from file system (Markdown files with YAML frontmatter)
Aligns with "skill-style" playbook design: file = executable spec
"""

import os
import yaml
import re
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging

from backend.app.models.playbook import Playbook, PlaybookMetadata

logger = logging.getLogger(__name__)


class PlaybookLoader:
    """Load Playbooks from file system"""

    def __init__(self, playbooks_dir: Optional[str] = None):
        """
        Initialize PlaybookLoader

        Args:
            playbooks_dir: Path to playbooks directory (default: docs/playbooks/)
        """
        if playbooks_dir is None:
            # Default to docs/playbooks/ relative to project root
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            playbooks_dir = os.path.join(base_dir, "docs", "playbooks")

        self.playbooks_dir = Path(playbooks_dir)
        if not self.playbooks_dir.exists():
            logger.warning(f"Playbooks directory does not exist: {self.playbooks_dir}")
            self.playbooks_dir.mkdir(parents=True, exist_ok=True)

    def parse_frontmatter(self, content: str) -> tuple[Dict[str, Any], str]:
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

    def _load_yaml_playbook(self, file_path: Path) -> Optional[Playbook]:
        """Load a single Playbook from a YAML file (for capability packs)"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse YAML (handle multiple documents separated by ---)
            # If file has multiple --- separators, only parse the first YAML document
            if content.strip().startswith('---'):
                # Split by --- and take the first YAML document
                parts = content.split('---', 2)
                if len(parts) >= 2:
                    yaml_content = parts[1].strip()
                else:
                    yaml_content = content
            else:
                yaml_content = content

            data = yaml.safe_load(yaml_content)
            if not data:
                return None

            # Convert YAML structure to Playbook model
            # Support both 'code' and 'playbook_code' for playbook_code field
            playbook_code = data.get('playbook_code') or data.get('code', file_path.stem)

            # Extract tags (support both list and string formats)
            tags = data.get('tags', [])
            if isinstance(tags, str):
                tags = [tags]

            # Build metadata with all available fields
            metadata_dict = {
                'playbook_code': playbook_code,
                'name': data.get('name', ''),
                'description': data.get('description', ''),
                'version': data.get('version', '0.1.0'),
                'locale': data.get('locale', 'zh-TW'),
                'tags': tags
            }

            # Add optional fields if present (only if they exist in PlaybookMetadata)
            if 'entry_agent_type' in data:
                metadata_dict['entry_agent_type'] = data['entry_agent_type']
            # Note: 'entrypoint' is not a PlaybookMetadata field, skip it
            if 'onboarding_task' in data:
                metadata_dict['onboarding_task'] = data['onboarding_task']
            if 'icon' in data:
                metadata_dict['icon'] = data['icon']
            if 'required_tools' in data:
                metadata_dict['required_tools'] = data['required_tools']
            if 'background' in data:
                metadata_dict['background'] = data['background']
            if 'optional_tools' in data:
                metadata_dict['optional_tools'] = data['optional_tools']

            # Handle kind field
            from backend.app.models.playbook import PlaybookKind
            kind_value = data.get('kind')
            if kind_value:
                try:
                    metadata_dict['kind'] = PlaybookKind(kind_value)
                except ValueError:
                    metadata_dict['kind'] = PlaybookKind.USER_WORKFLOW
            else:
                metadata_dict['kind'] = PlaybookKind.USER_WORKFLOW

            metadata = PlaybookMetadata(**metadata_dict)

            # Extract SOP content (markdown after YAML frontmatter separator)
            sop_content = ""
            if '---' in content:
                # Split on YAML frontmatter separator
                parts = content.split('---', 2)
                if len(parts) > 2:
                    sop_content = parts[2].strip()

            playbook = Playbook(
                metadata=metadata,
                sop_content=sop_content
            )

            return playbook

        except Exception as e:
            logger.error(f"Failed to load YAML playbook from {file_path}: {e}")
            return None

    def load_playbook_from_file(self, file_path: Path) -> Optional[Playbook]:
        """Load a single Playbook from a Markdown file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            frontmatter, sop_content = self.parse_frontmatter(content)

            # Extract locale from filename first (e.g., weekly_review_onboarding.en.md -> en)
            filename = file_path.stem
            inferred_locale = None
            if filename.endswith('.en'):
                inferred_locale = 'en'
                # Remove .en suffix to get base playbook_code
                base_code = filename[:-3]  # Remove '.en'
            else:
                inferred_locale = 'zh-TW'
                base_code = filename

            # Extract required fields
            playbook_code = frontmatter.get('playbook_code')
            if not playbook_code:
                # Use base code from filename (without locale suffix)
                playbook_code = base_code
            else:
                # If frontmatter has playbook_code, remove .en suffix if present
                playbook_code = playbook_code.replace('.en', '')

            # Extract locale (prefer frontmatter, but enforce filename-based locale for .en.md files)
            frontmatter_locale = frontmatter.get('locale')
            if filename.endswith('.en'):
                # For .en.md files, always use 'en' locale regardless of frontmatter
                locale = 'en'
            else:
                # For other files, prefer frontmatter, fallback to inferred
                locale = frontmatter_locale if frontmatter_locale in ['zh-TW', 'en'] else inferred_locale

            if locale not in ['zh-TW', 'en']:
                logger.warning(f"Unsupported locale {locale} for {playbook_code}, skipping")
                return None

            from backend.app.models.playbook import PlaybookKind

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
            )

            # Build Playbook
            playbook = Playbook(
                metadata=metadata,
                sop_content=sop_content.strip()
            )

            return playbook

        except Exception as e:
            logger.error(f"Failed to load playbook from {file_path}: {e}")
            return None

    def load_all_playbooks(self) -> List[Playbook]:
        """Load all Playbooks from the playbooks directory and capability packs"""
        playbooks = []

        # Load from main playbooks directory (docs/playbooks/)
        if self.playbooks_dir.exists():
            # Find all .md files (excluding README.md)
            for file_path in self.playbooks_dir.glob('*.md'):
                if file_path.name == 'README.md':
                    continue

                playbook = self.load_playbook_from_file(file_path)
                if playbook:
                    playbooks.append(playbook)

            # Also load .yaml files from main playbooks directory
            for file_path in self.playbooks_dir.glob('*.yaml'):
                try:
                    playbook = self._load_yaml_playbook(file_path)
                    if playbook:
                        playbooks.append(playbook)
                except Exception as e:
                    logger.warning(f"Failed to load YAML playbook from {file_path}: {e}")
        else:
            logger.warning(f"Playbooks directory does not exist: {self.playbooks_dir}")

        # Also load from backend/playbooks/ directory (legacy format, for backward compatibility)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        backend_playbooks_dir = Path(base_dir) / "backend" / "playbooks"
        if backend_playbooks_dir.exists():
            # Load .yaml files from backend/playbooks/ (legacy format)
            for file_path in backend_playbooks_dir.glob('*.yaml'):
                try:
                    playbook = self._load_yaml_playbook(file_path)
                    if playbook:
                        # Check if already loaded (avoid duplicates)
                        if not any(p.metadata.playbook_code == playbook.metadata.playbook_code
                                 and p.metadata.locale == playbook.metadata.locale
                                 for p in playbooks):
                            playbooks.append(playbook)
                            logger.debug(f"Loaded playbook {playbook.metadata.playbook_code} from {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to load YAML playbook from {file_path}: {e}")

        # Load from backend/i18n/playbooks/ directory (new architecture: organized by locale)
        i18n_playbooks_dir = Path(base_dir) / "backend" / "i18n" / "playbooks"
        if i18n_playbooks_dir.exists():
            # Supported locales
            supported_locales = ['zh-TW', 'en', 'ja']
            for locale in supported_locales:
                locale_dir = i18n_playbooks_dir / locale
                if locale_dir.exists():
                    # Load .md files from locale directory (new architecture: playbook.md + playbook.json)
                    for file_path in locale_dir.glob('*.md'):
                        if file_path.name == 'README.md':
                            continue
                        try:
                            playbook = self.load_playbook_from_file(file_path)
                            if playbook:
                                # Ensure locale matches directory
                                if playbook.metadata.locale != locale:
                                    # Update locale to match directory
                                    playbook.metadata.locale = locale
                                # Check if already loaded (avoid duplicates)
                                if not any(p.metadata.playbook_code == playbook.metadata.playbook_code
                                         and p.metadata.locale == playbook.metadata.locale
                                         for p in playbooks):
                                    playbooks.append(playbook)
                                    logger.debug(f"Loaded playbook {playbook.metadata.playbook_code} ({locale}) from {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to load MD playbook from {file_path}: {e}")

        # Load from capability packs
        try:
            from backend.app.services.capability_installer import CapabilityInstaller
            installer = CapabilityInstaller()
            installed = installer.list_installed()

            for cap in installed:
                target_dir_str = cap.get('target_dir')
                if target_dir_str:
                    cap_dir = Path(target_dir_str)
                else:
                    cap_dir = None
                if not cap_dir or not cap_dir.exists():
                    # Try to construct path from capability id if target_dir is missing
                    cap_id = cap.get('id', '')
                    if cap_id:
                        # Extract capability name from id (e.g., "mindscape.storyboard" -> "storyboard")
                        cap_name = cap_id.split('.')[-1] if '.' in cap_id else cap_id
                        # Try to find capability directory in app/capabilities
                        app_dir = Path(__file__).parent.parent
                        cap_dir = app_dir / "capabilities" / cap_name
                        if not cap_dir.exists():
                            logger.debug(f"Capability directory not found: {cap_dir} for cap_id: {cap_id}")
                            continue
                    else:
                        continue

                playbooks_dir = cap_dir / "playbooks"
                if playbooks_dir.exists():
                    # Load .yaml playbooks from capability pack
                    for yaml_file in playbooks_dir.glob('*.yaml'):
                        try:
                            # Try to load as YAML playbook
                            playbook = self._load_yaml_playbook(yaml_file)
                            if playbook:
                                playbooks.append(playbook)
                                logger.debug(f"Loaded playbook {playbook.metadata.playbook_code} from {yaml_file}")
                        except Exception as e:
                            logger.warning(f"Failed to load playbook from {yaml_file}: {e}")
                else:
                    logger.debug(f"Playbooks directory does not exist: {playbooks_dir} for cap_id: {cap.get('id', 'unknown')}")
        except Exception as e:
            logger.warning(f"Failed to load playbooks from capability packs: {e}")

        logger.info(f"Loaded {len(playbooks)} playbooks (from main dir + capability packs)")
        return playbooks

    def get_playbook_by_code(self, playbook_code: str, locale: Optional[str] = None) -> Optional[Playbook]:
        """
        Get a specific Playbook by code

        Args:
            playbook_code: Base playbook code (without locale suffix)
            locale: Preferred locale for file selection (e.g., 'zh-TW', 'en').
                    If specified, returns the matching locale version if available.
                    If None, returns the first found (no preference).
        """
        # First, try loading all playbooks and find by code
        all_playbooks = self.load_all_playbooks()

        # Filter by playbook_code
        matching = [p for p in all_playbooks if p.metadata.playbook_code == playbook_code]

        if not matching:
            return None

        # If locale specified, prefer matching locale
        if locale:
            locale_match = [p for p in matching if p.metadata.locale == locale]
            if locale_match:
                return locale_match[0]

        # Return first match (prefer zh-TW if available)
        zh_tw_match = [p for p in matching if p.metadata.locale == 'zh-TW']
        if zh_tw_match:
            return zh_tw_match[0]

        # Otherwise return first match
        return matching[0]

    def get_playbook_manifest(self, playbook_code: str) -> Optional[Dict[str, Any]]:
        """
        Get Playbook manifest (frontmatter only) for routing/scoring
        This is the "skill-style" machine-readable spec
        """
        playbook = self.get_playbook_by_code(playbook_code)
        if not playbook:
            return None

        # Return manifest (metadata + routing info)
        manifest = {
            'playbook_code': playbook.metadata.playbook_code,
            'version': playbook.metadata.version,
            'name': playbook.metadata.name,
            'description': playbook.metadata.description,
            'tags': playbook.metadata.tags,
            'entry_agent_type': getattr(playbook.metadata, 'entry_agent_type', None),
            'mindscape_requirements': getattr(playbook.metadata, 'mindscape_requirements', {}),
            'icon': getattr(playbook.metadata, 'icon', None),
        }

        return manifest

    def validate_playbook(self, playbook: Playbook) -> List[str]:
        """
        Validate Playbook format

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Required fields
        if not playbook.metadata.playbook_code:
            errors.append("Missing playbook_code")
        if not playbook.metadata.name:
            errors.append("Missing name")

        # Locale validation
        if playbook.metadata.locale not in ['zh-TW', 'en']:
            errors.append(f"Invalid locale: {playbook.metadata.locale}")

        # Onboarding task validation
        if playbook.metadata.onboarding_task:
            if playbook.metadata.onboarding_task not in ['task1', 'task2', 'task3']:
                errors.append(f"Invalid onboarding_task: {playbook.metadata.onboarding_task}")

        return errors

    def reindex_playbooks(self, store) -> Dict[str, Any]:
        """
        Re-scan and index all Playbooks to database

        Args:
            store: PlaybookStore instance

        Returns:
            Summary of indexing results
        """
        results = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }

        playbooks = self.load_all_playbooks()
        results["total"] = len(playbooks)

        for playbook in playbooks:
            # Validate
            errors = self.validate_playbook(playbook)
            if errors:
                results["failed"] += 1
                results["errors"].append({
                    "playbook_code": playbook.metadata.playbook_code,
                    "errors": errors
                })
                continue

            # Save to database
            try:
                existing = store.get_playbook(playbook.metadata.playbook_code)
                if existing:
                    # Update
                    store.update_playbook(playbook.metadata.playbook_code, {
                        "name": playbook.metadata.name,
                        "description": playbook.metadata.description,
                        "tags": playbook.metadata.tags,
                        "sop_content": playbook.sop_content,
                    })
                else:
                    # Create
                    store.create_playbook(playbook)

                results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "playbook_code": playbook.metadata.playbook_code,
                    "error": str(e)
                })

        return results

