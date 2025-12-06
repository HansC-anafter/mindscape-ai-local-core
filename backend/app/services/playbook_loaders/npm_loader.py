"""
Playbook NPM Package Loader
Loads playbooks from NPM packages (independent playbook repositories)
"""

import json
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import os

from backend.app.models.playbook import PlaybookJson

logger = logging.getLogger(__name__)


class PlaybookNpmLoader:
    """Loads playbooks from NPM packages"""

    @staticmethod
    def find_node_modules_path() -> Optional[Path]:
        """
        Find node_modules directory
        Looks for node_modules in current directory and parent directories
        """
        current = Path(__file__).resolve()
        
        # Start from backend directory and go up
        for parent in [current.parent.parent.parent.parent, current.parent.parent.parent]:
            node_modules = parent / "node_modules"
            if node_modules.exists() and node_modules.is_dir():
                return node_modules
        
        # Also check if we're in a monorepo structure
        workspace_root = current.parent.parent.parent.parent
        node_modules = workspace_root / "node_modules"
        if node_modules.exists():
            return node_modules
        
        return None

    @staticmethod
    def find_playbook_packages() -> list[Dict[str, Any]]:
        """
        Find all installed @mindscape/playbook-* packages
        
        Returns:
            List of package info dicts with keys: name, version, path, playbook_code
        """
        node_modules = PlaybookNpmLoader.find_node_modules_path()
        if not node_modules:
            logger.debug("node_modules not found, skipping NPM playbook discovery")
            return []

        playbooks = []
        mindscape_dir = node_modules / "@mindscape"
        
        if not mindscape_dir.exists():
            return []

        try:
            for item in mindscape_dir.iterdir():
                if item.is_dir() and item.name.startswith("playbook-"):
                    package_json_path = item / "package.json"
                    if not package_json_path.exists():
                        continue

                    try:
                        with open(package_json_path, 'r', encoding='utf-8') as f:
                            package_data = json.load(f)
                        
                        # Check if it's a playbook package
                        mindscape_meta = package_data.get("mindscape", {})
                        if mindscape_meta.get("type") == "playbook":
                            playbooks.append({
                                "name": package_data.get("name", item.name),
                                "version": package_data.get("version", "unknown"),
                                "path": str(item),
                                "playbook_code": mindscape_meta.get("playbook_code") or item.name.replace("playbook-", "").replace("-", "_")
                            })
                    except Exception as e:
                        logger.warning(f"Failed to read package.json from {item}: {e}")
                        continue
        except Exception as e:
            logger.warning(f"Failed to scan @mindscape directory: {e}")

        return playbooks

    @staticmethod
    def load_playbook_json(playbook_code: str) -> Optional[PlaybookJson]:
        """
        Load playbook.json from NPM package
        
        Args:
            playbook_code: Playbook code
            
        Returns:
            PlaybookJson model or None if not found
        """
        packages = PlaybookNpmLoader.find_playbook_packages()
        
        for package in packages:
            if package["playbook_code"] == playbook_code:
                playbook_dir = Path(package["path"])
                
                # Try common locations for playbook.json
                possible_paths = [
                    playbook_dir / "playbook" / f"{playbook_code}.json",
                    playbook_dir / "playbook" / "playbook.json",
                    playbook_dir / f"{playbook_code}.json",
                    playbook_dir / "playbook.json",
                ]
                
                for json_path in possible_paths:
                    if json_path.exists():
                        try:
                            with open(json_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            
                            # Validate playbook_code matches
                            if data.get("playbook_code") == playbook_code:
                                return PlaybookJson(**data)
                        except Exception as e:
                            logger.error(f"Failed to load playbook.json from {json_path}: {e}")
                            continue

        return None

    @staticmethod
    def load_playbook_i18n(playbook_code: str, locale: str = "zh-TW") -> Optional[str]:
        """
        Load playbook i18n markdown from NPM package
        
        Args:
            playbook_code: Playbook code
            locale: Language locale
            
        Returns:
            Markdown content or None if not found
        """
        packages = PlaybookNpmLoader.find_playbook_packages()
        
        for package in packages:
            if package["playbook_code"] == playbook_code:
                playbook_dir = Path(package["path"])
                
                # Try common locations for i18n files
                possible_paths = [
                    playbook_dir / "playbook" / "i18n" / locale / f"{playbook_code}.md",
                    playbook_dir / "playbook" / "i18n" / locale / "playbook.md",
                    playbook_dir / "playbook" / f"{playbook_code}.md",
                    playbook_dir / "playbook" / "playbook.md",
                    playbook_dir / "i18n" / locale / f"{playbook_code}.md",
                ]
                
                for md_path in possible_paths:
                    if md_path.exists():
                        try:
                            with open(md_path, 'r', encoding='utf-8') as f:
                                return f.read()
                        except Exception as e:
                            logger.error(f"Failed to load i18n from {md_path}: {e}")
                            continue

        return None

