"""
Playbook JSON Loader
Loads playbook.json files for structured workflow definitions
"""

import json
import logging
from typing import Optional
from pathlib import Path

from backend.app.models.playbook import PlaybookJson

logger = logging.getLogger(__name__)


class PlaybookJsonLoader:
    """Loads playbook.json files"""

    @staticmethod
    def load_playbook_json(playbook_code: str) -> Optional[PlaybookJson]:
        """
        Load playbook.json file for a given playbook code

        Args:
            playbook_code: Playbook code

        Returns:
            PlaybookJson model or None if not found
        """
        base_dir = Path(__file__).parent.parent.parent.parent

        possible_paths = [
            base_dir / "backend" / "playbooks" / "specs" / f"{playbook_code}.json",
            base_dir / "backend" / "playbooks" / f"{playbook_code}.json",
        ]
        for locale in ['zh-TW', 'en', 'ja']:
            possible_paths.append(
                base_dir / "backend" / "i18n" / "playbooks" / locale / f"{playbook_code}.json"
            )

        for playbook_json_path in possible_paths:
            if playbook_json_path.exists():
                try:
                    with open(playbook_json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    return PlaybookJson(**data)
                except Exception as e:
                    logger.error(f"Failed to load playbook.json from {playbook_json_path}: {e}")
                    continue

        logger.debug(f"playbook.json not found for {playbook_code} in any of the expected locations")
        return None

