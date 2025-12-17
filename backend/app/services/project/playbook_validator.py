"""
Playbook Sequence Validator
Unified validation logic for playbook sequences before they enter flows
"""

import logging
from typing import List
from pathlib import Path

from backend.app.services.playbook_loaders.file_loader import PlaybookFileLoader
from backend.app.services.playbook_loaders.json_loader import PlaybookJsonLoader

logger = logging.getLogger(__name__)


def validate_playbook_sequence(playbook_sequence: List[str], base_dir: Path = None) -> List[str]:
    """
    Validate playbook sequence and return only existing playbooks

    Args:
        playbook_sequence: List of playbook codes to validate
        base_dir: Base directory for playbook files (defaults to backend root)

    Returns:
        List of validated playbook codes that exist
    """
    if not playbook_sequence:
        return []

    if base_dir is None:
        # Default to backend root
        current_file = Path(__file__)
        base_dir = current_file.parent.parent.parent.parent

    validated_sequence = []

    for playbook_code in playbook_sequence:
        if not playbook_code or not isinstance(playbook_code, str):
            logger.warning(f"Invalid playbook code: {playbook_code}, skipping")
            continue

        playbook_exists = False

        # Check if playbook exists in file system (i18n markdown files)
        for locale in ['zh-TW', 'en', 'ja']:
            i18n_dir = base_dir / "backend" / "i18n" / "playbooks" / locale
            md_file = i18n_dir / f"{playbook_code}.md"

            if md_file.exists():
                try:
                    playbook = PlaybookFileLoader.load_playbook_from_file(md_file)
                    if playbook:
                        playbook_exists = True
                        break
                except Exception as e:
                    logger.debug(f"Failed to load playbook {playbook_code} from {locale} markdown: {e}")

        # Also check JSON specs
        if not playbook_exists:
            try:
                playbook_json = PlaybookJsonLoader.load_playbook_json(playbook_code)
                if playbook_json:
                    playbook_exists = True
            except Exception as e:
                logger.debug(f"Failed to load playbook {playbook_code} from JSON: {e}")

        if playbook_exists:
            validated_sequence.append(playbook_code)
        else:
            logger.warning(f"Playbook {playbook_code} does not exist, skipping from sequence")

    if len(playbook_sequence) > len(validated_sequence):
        logger.warning(
            f"Playbook sequence validation: {len(playbook_sequence)} suggested, "
            f"but only {len(validated_sequence)} exist"
        )

    return validated_sequence

