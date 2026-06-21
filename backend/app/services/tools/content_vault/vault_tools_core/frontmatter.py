"""YAML frontmatter parsing for content vault Markdown files."""

import logging
import re

import yaml

logger = logging.getLogger(__name__)


def parse_frontmatter(content: str) -> tuple:
    """
    Parse YAML frontmatter from Markdown content.

    Returns:
        Tuple of frontmatter dictionary and body content.
    """
    frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(frontmatter_pattern, content, re.DOTALL)

    if match:
        frontmatter_str = match.group(1)
        body = match.group(2)
        try:
            frontmatter = yaml.safe_load(frontmatter_str) or {}
            return frontmatter, body
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse frontmatter YAML: {e}")
            return {}, content

    return {}, content
