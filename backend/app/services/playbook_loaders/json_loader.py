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
        
        Tries to load from:
        1. NPM packages (@mindscape/playbook-*)
        2. Core playbooks directory (backward compatibility)

        Args:
            playbook_code: Playbook code

        Returns:
            PlaybookJson model or None if not found
        """
        # First try NPM packages
        try:
            from .npm_loader import PlaybookNpmLoader
            npm_result = PlaybookNpmLoader.load_playbook_json(playbook_code)
            if npm_result:
                logger.debug(f"Loaded playbook.json for {playbook_code} from NPM package")
                return npm_result
        except Exception as e:
            logger.debug(f"Failed to load from NPM package: {e}")

        # Fallback to core playbooks directory (backward compatibility)
        base_dir = Path(__file__).parent.parent.parent.parent

        possible_paths = [
            base_dir / "playbooks" / "specs" / f"{playbook_code}.json",
            base_dir / "playbooks" / f"{playbook_code}.json",
        ]
        for locale in ['zh-TW', 'en', 'ja']:
            possible_paths.append(
                base_dir / "i18n" / "playbooks" / locale / f"{playbook_code}.json"
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

    @staticmethod
    def save_playbook_json(playbook_code: str, playbook_json: PlaybookJson, locale: str = "zh-TW") -> bool:
        """
        Save playbook.json file for a given playbook code

        Args:
            playbook_code: Playbook code
            playbook_json: PlaybookJson model to save
            locale: Language locale (default: zh-TW)

        Returns:
            True if saved successfully, False otherwise
        """
        base_dir = Path(__file__).parent.parent.parent.parent

        # Determine save path based on locale
        if locale in ['zh-TW', 'en', 'ja']:
            save_path = base_dir / "i18n" / "playbooks" / locale / f"{playbook_code}.json"
        else:
            # Default to specs directory
            save_path = base_dir / "playbooks" / "specs" / f"{playbook_code}.json"

        try:
            # Ensure directory exists
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert to dict and save
            data = playbook_json.model_dump(exclude_none=True)
            with open(save_path, 'w', encoding='utf-8') as f:
                import json
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"Saved playbook.json for {playbook_code} to {save_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save playbook.json for {playbook_code} to {save_path}: {e}")
            return False

