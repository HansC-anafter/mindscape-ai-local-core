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
    def load_playbook_json(playbook_code: str, capability_code: Optional[str] = None) -> Optional[PlaybookJson]:
        """
        Load playbook.json file for a given playbook code

        Tries to load from:
        1. Cloud providers (via CloudExtensionManager) - if capability_code is provided
        2. NPM packages (@mindscape/playbook-*)
        3. Core playbooks directory (backward compatibility)

        Note: Cloud capabilities playbook JSON specs should be accessed via
        CloudExtensionManager (configured through settings page cloud_providers),
        not through hardcoded environment variables or direct API calls.
        Direct file system access to cloud capabilities is prohibited to maintain
        architecture boundaries.

        Args:
            playbook_code: Playbook code
            capability_code: Optional capability code for cloud playbooks

        Returns:
            PlaybookJson model or None if not found
        """
        # Try cloud providers first (if capability_code is provided)
        if capability_code:
            try:
                import asyncio
                from ...services.cloud_extension_manager import CloudExtensionManager

                manager = CloudExtensionManager.instance()
                
                # Try to get existing event loop, or create new one if not in async context
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is running, we can't use asyncio.run()
                        # This is a synchronous method, so we'll skip cloud provider loading
                        # and let async callers handle it through PlaybookService
                        logger.debug("Event loop is running, skipping synchronous cloud provider load")
                    else:
                        playbook_data = loop.run_until_complete(
                            manager.get_playbook_from_any_provider(
                                capability_code=capability_code,
                                playbook_code=playbook_code,
                                locale="zh-TW"
                            )
                        )
                        if playbook_data:
                            playbook_dict = playbook_data.get("playbook") if isinstance(playbook_data, dict) else playbook_data
                            if playbook_dict:
                                try:
                                    return PlaybookJson(**playbook_dict)
                                except Exception as e:
                                    logger.debug(f"Failed to parse playbook JSON from cloud provider: {e}")
                except RuntimeError:
                    # No event loop, create new one
                    playbook_data = asyncio.run(
                        manager.get_playbook_from_any_provider(
                            capability_code=capability_code,
                            playbook_code=playbook_code,
                            locale="zh-TW"
                        )
                    )
                    if playbook_data:
                        playbook_dict = playbook_data.get("playbook") if isinstance(playbook_data, dict) else playbook_data
                        if playbook_dict:
                            try:
                                return PlaybookJson(**playbook_dict)
                            except Exception as e:
                                logger.debug(f"Failed to parse playbook JSON from cloud provider: {e}")
            except Exception as e:
                logger.debug(f"Failed to load from cloud provider: {e}")

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

        # Note: Cloud capabilities playbook JSON specs should be accessed via
        # CloudExtensionManager (configured through settings page cloud_providers),
        # not through hardcoded environment variables or direct API calls.
        # This maintains architecture boundaries and allows users to configure
        # external playbook remotes through the UI.

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

