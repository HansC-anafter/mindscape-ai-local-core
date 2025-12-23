#!/usr/bin/env python3
"""
Content Vault Initialization Script

Automatically initializes Content Vault directory structure and templates.
Can be called:
1. During capability pack installation (post-install hook)
2. On first startup (if vault doesn't exist)
3. Manually via command line

Usage:
    python backend/scripts/init_content_vault.py [--vault-path PATH] [--force]
"""

import argparse
import sys
from pathlib import Path
from typing import Optional
import yaml
import logging

# Add parent directory to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

logger = logging.getLogger(__name__)


def get_default_vault_path() -> Path:
    """Get default vault path (user home directory)"""
    import os
    home = Path.home()
    return home / "content-vault"


def create_vault_structure(vault_path: Path, force: bool = False) -> bool:
    """
    Create Content Vault directory structure

    Args:
        vault_path: Path to content vault
        force: If True, recreate even if vault exists

    Returns:
        True if successful
    """
    directories = [
        "series",
        "arcs",
        "posts/instagram",
        "posts/facebook",
        "drafts/ideas",
        "assets/images",
        "assets/templates",
        "assets/style-guides",
    ]

    if vault_path.exists() and not force:
        missing_dirs = []
        for dir_path in directories:
            full_path = vault_path / dir_path
            if not full_path.exists():
                missing_dirs.append(dir_path)

        if missing_dirs:
            logger.info(f"Content Vault exists but missing subdirectories, creating: {missing_dirs}")
            for dir_path in missing_dirs:
                full_path = vault_path / dir_path
                full_path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Created missing directory: {full_path}")
            return True
        else:
            logger.info(f"Content Vault already exists at {vault_path}")
            return True

    try:
        for dir_path in directories:
            full_path = vault_path / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directory: {full_path}")

        logger.info(f"Created Content Vault structure at {vault_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to create vault structure: {e}")
        return False


def create_vault_config(vault_path: Path, force: bool = False) -> bool:
    """
    Create .vault-config.yaml file

    Args:
        vault_path: Path to content vault
        force: If True, overwrite existing config

    Returns:
        True if successful
    """
    config_path = vault_path / ".vault-config.yaml"

    if config_path.exists() and not force:
        logger.info(f"Vault config already exists at {config_path}")
        return True

    try:
        config = {
            "vault_version": "1.0",
            "default_platform": "instagram",
            "default_series": "mindful-coffee",
        }

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        logger.info(f"Created vault config at {config_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to create vault config: {e}")
        return False


def copy_templates(vault_path: Path, force: bool = False) -> bool:
    """
    Copy template files to vault assets/templates directory

    Args:
        vault_path: Path to content vault
        force: If True, overwrite existing templates

    Returns:
        True if successful
    """
    # Template source directory (in local-core)
    script_dir = Path(__file__).parent
    source_templates_dir = script_dir.parent.parent / "content-vault" / "assets" / "templates"
    target_templates_dir = vault_path / "assets" / "templates"

    if not source_templates_dir.exists():
        logger.warning(f"Source templates directory not found: {source_templates_dir}")
        logger.info("Templates will be created from specification")
        return create_templates_from_spec(vault_path, force)

    try:
        target_templates_dir.mkdir(parents=True, exist_ok=True)

        template_files = [
            "series-template.md",
            "arc-template.md",
            "post-template.md",
        ]

        copied = 0
        for template_file in template_files:
            source = source_templates_dir / template_file
            target = target_templates_dir / template_file

            if target.exists() and not force:
                logger.debug(f"Template already exists: {target}")
                continue

            if source.exists():
                import shutil
                shutil.copy2(source, target)
                logger.debug(f"Copied template: {template_file}")
                copied += 1
            else:
                logger.warning(f"Template not found: {source}")

        if copied > 0:
            logger.info(f"Copied {copied} template files to {target_templates_dir}")
        else:
            logger.info("All templates already exist")

        return True

    except Exception as e:
        logger.error(f"Failed to copy templates: {e}")
        return False


def create_templates_from_spec(vault_path: Path, force: bool = False) -> bool:
    """
    Create templates from specification (fallback if source templates don't exist)

    Args:
        vault_path: Path to content vault
        force: If True, overwrite existing templates

    Returns:
        True if successful
    """
    templates_dir = vault_path / "assets" / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    # Series template
    series_template = """---
doc_type: series
series_id: {{ SERIES_ID }}
title: "{{ TITLE }}"
platform: instagram
status: active

theme: "{{ THEME }}"
tone: "{{ TONE }}"
target_audience: "{{ AUDIENCE }}"

content_pillars:
  - pillar_1
  - pillar_2

style_guide:
  voice: "First person, like chatting with friends"
  length: "100-250 characters"
  hashtags_count: "5-8"
  emoji_style: "Use sparingly"

visual_style:
  colors: []
  mood: "Warm, gentle"

created_at: {{ DATE }}
---

# {{ TITLE }}

## Series Introduction

(Describe the core concept and goals)

## Narrative Strategy

1.
2.

## Future Direction

-
"""

    # Arc template
    arc_template = """---
doc_type: arc
arc_id: {{ ARC_ID }}
series_id: {{ SERIES_ID }}
title: "{{ TITLE }}"

start_date: {{ START_DATE }}
end_date: {{ END_DATE }}
duration_weeks: {{ WEEKS }}

arc_theme: "{{ ARC_THEME }}"
narrative_structure:
  - setup: "{{ SETUP }}"
  - development: "{{ DEVELOPMENT }}"
  - climax: "{{ CLIMAX }}"
  - resolution: "{{ RESOLUTION }}"

emotional_arc:
  - phase: "{{ PHASE_1 }}"
    tone: "{{ TONE_1 }}"
    posts: {{ COUNT_1 }}

key_messages:
  - "{{ MESSAGE_1 }}"

status: planning
---

# {{ TITLE }}

## Arc Background

(Why design this arc?)

## Narrative Rhythm

Week 1:
-

Week 2:
-
"""

    # Post template
    post_template = """---
doc_type: post
post_id: {{ POST_ID }}
series_id: {{ SERIES_ID }}
arc_id: {{ ARC_ID }}

platform: instagram
post_type: single_image
sequence: {{ SEQUENCE }}
date: {{ DATE }}
status: draft

narrative_phase: "{{ PHASE }}"
emotion: "{{ EMOTION }}"
---

# Post Content

{{ CONTENT }}

{{ HASHTAGS }}

---

## Creation Notes

**Inspiration Source**:

**Narrative Techniques**:

**Arc Connection**:
"""

    templates = {
        "series-template.md": series_template,
        "arc-template.md": arc_template,
        "post-template.md": post_template,
    }

    try:
        created = 0
        for filename, content in templates.items():
            template_path = templates_dir / filename
            if template_path.exists() and not force:
                continue

            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(content)
            created += 1

        if created > 0:
            logger.info(f"Created {created} template files from specification")
        return True

    except Exception as e:
        logger.error(f"Failed to create templates: {e}")
        return False


def initialize_content_vault(
    vault_path: Optional[Path] = None,
    force: bool = False
) -> bool:
    """
    Initialize Content Vault (complete setup)

    Args:
        vault_path: Path to content vault (default: ~/content-vault)
        force: If True, recreate even if vault exists

    Returns:
        True if successful
    """
    if vault_path is None:
        vault_path = get_default_vault_path()

    vault_path = Path(vault_path).expanduser().resolve()

    logger.info(f"Initializing Content Vault at {vault_path}")

    # 1. Create directory structure
    if not create_vault_structure(vault_path, force):
        return False

    # 2. Create vault config
    if not create_vault_config(vault_path, force):
        return False

    # 3. Copy/create templates
    if not copy_templates(vault_path, force):
        return False

    logger.info(f"Content Vault initialized successfully at {vault_path}")
    return True


def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(
        description="Initialize Content Vault directory structure and templates"
    )
    parser.add_argument(
        "--vault-path",
        type=str,
        help="Path to content vault (default: ~/content-vault)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recreate vault even if it exists"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    vault_path = Path(args.vault_path) if args.vault_path else None

    success = initialize_content_vault(vault_path, args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

