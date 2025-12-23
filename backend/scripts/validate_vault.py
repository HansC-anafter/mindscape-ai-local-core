#!/usr/bin/env python3
"""
Content Vault Validator

Validates Content Vault documents against specification.
Checks required fields, field types, enum values, and document structure.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import yaml
import re
import logging
from datetime import datetime

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from backend.app.services.tools.content_vault.vault_tools import parse_frontmatter

logger = logging.getLogger(__name__)


class VaultValidator:
    """Content Vault specification validator"""

    REQUIRED_FIELDS = {
        'series': ['doc_type', 'series_id', 'title', 'platform', 'status'],
        'arc': ['doc_type', 'arc_id', 'series_id', 'title', 'start_date', 'end_date'],
        'post': ['doc_type', 'post_id', 'series_id', 'platform', 'sequence', 'date', 'status']
    }

    OPTIONAL_FIELDS = {
        'series': ['theme', 'tone', 'target_audience', 'content_pillars', 'style_guide', 'visual_style'],
        'arc': ['arc_theme', 'narrative_structure', 'emotional_arc', 'key_messages', 'duration_weeks'],
        'post': ['arc_id', 'post_type', 'narrative_phase', 'emotion', 'word_count', 'hashtags_count']
    }

    ENUM_VALUES = {
        'doc_type': ['series', 'arc', 'post'],
        'platform': ['instagram', 'facebook', 'twitter', 'linkedin'],
        'status': ['active', 'inactive', 'archived', 'draft', 'scheduled', 'published'],
        'post_type': ['single_image', 'carousel', 'reel', 'story', 'video']
    }

    FIELD_TYPES = {
        'doc_type': str,
        'series_id': str,
        'arc_id': str,
        'post_id': str,
        'title': str,
        'platform': str,
        'status': str,
        'sequence': int,
        'date': str,
        'start_date': str,
        'end_date': str,
        'theme': str,
        'tone': str,
        'target_audience': str,
        'content_pillars': list,
        'style_guide': dict,
        'visual_style': dict,
        'arc_theme': str,
        'narrative_structure': list,
        'emotional_arc': list,
        'key_messages': list,
        'post_type': str,
        'narrative_phase': str,
        'emotion': str,
        'word_count': int,
        'hashtags_count': int,
        'duration_weeks': int
    }

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []

    def validate_vault(self) -> Tuple[bool, List[Dict], List[Dict]]:
        """
        Validate entire vault

        Returns:
            (is_valid, errors, warnings)
        """
        if not self.vault_path.exists():
            self.errors.append({
                'file': str(self.vault_path),
                'message': f'Vault path does not exist: {self.vault_path}'
            })
            return False, self.errors, self.warnings

        self._validate_series()
        self._validate_arcs()
        self._validate_posts()

        is_valid = len(self.errors) == 0
        return is_valid, self.errors, self.warnings

    def _validate_series(self):
        """Validate series documents"""
        series_dir = self.vault_path / "series"
        if not series_dir.exists():
            self.warnings.append({
                'file': str(series_dir),
                'message': 'Series directory does not exist'
            })
            return

        for md_file in series_dir.glob("*.md"):
            try:
                self._validate_document(md_file, 'series')
            except Exception as e:
                self.errors.append({
                    'file': str(md_file),
                    'message': f'Failed to validate series document: {e}'
                })

    def _validate_arcs(self):
        """Validate arc documents"""
        arcs_dir = self.vault_path / "arcs"
        if not arcs_dir.exists():
            self.warnings.append({
                'file': str(arcs_dir),
                'message': 'Arcs directory does not exist'
            })
            return

        for md_file in arcs_dir.glob("*.md"):
            try:
                self._validate_document(md_file, 'arc')
            except Exception as e:
                self.errors.append({
                    'file': str(md_file),
                    'message': f'Failed to validate arc document: {e}'
                })

    def _validate_posts(self):
        """Validate post documents"""
        posts_base_dir = self.vault_path / "posts"
        if not posts_base_dir.exists():
            self.warnings.append({
                'file': str(posts_base_dir),
                'message': 'Posts directory does not exist'
            })
            return

        for platform_dir in posts_base_dir.iterdir():
            if not platform_dir.is_dir():
                continue

            for md_file in platform_dir.glob("*.md"):
                try:
                    self._validate_document(md_file, 'post')
                except Exception as e:
                    self.errors.append({
                        'file': str(md_file),
                        'message': f'Failed to validate post document: {e}'
                    })

    def _validate_document(self, file_path: Path, doc_type: str):
        """
        Validate a single document

        Args:
            file_path: Path to markdown file
            doc_type: Expected document type ('series', 'arc', 'post')
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)

        if not frontmatter:
            self.errors.append({
                'file': str(file_path),
                'message': 'Missing YAML frontmatter'
            })
            return

        actual_doc_type = frontmatter.get('doc_type')
        if actual_doc_type != doc_type:
            self.errors.append({
                'file': str(file_path),
                'message': f'Document type mismatch: expected {doc_type}, got {actual_doc_type}'
            })

        self._validate_required_fields(file_path, frontmatter, doc_type)
        self._validate_field_types(file_path, frontmatter, doc_type)
        self._validate_enum_values(file_path, frontmatter, doc_type)
        self._validate_date_formats(file_path, frontmatter, doc_type)

    def _validate_required_fields(self, file_path: Path, frontmatter: Dict, doc_type: str):
        """Validate required fields"""
        required = self.REQUIRED_FIELDS.get(doc_type, [])
        for field in required:
            if field not in frontmatter:
                self.errors.append({
                    'file': str(file_path),
                    'message': f'Missing required field: {field}'
                })

    def _validate_field_types(self, file_path: Path, frontmatter: Dict, doc_type: str):
        """Validate field types"""
        for field, expected_type in self.FIELD_TYPES.items():
            if field not in frontmatter:
                continue

            value = frontmatter[field]
            if not isinstance(value, expected_type):
                self.errors.append({
                    'file': str(file_path),
                    'message': f'Field {field} has wrong type: expected {expected_type.__name__}, got {type(value).__name__}'
                })

    def _validate_enum_values(self, file_path: Path, frontmatter: Dict, doc_type: str):
        """Validate enum values"""
        for field, allowed_values in self.ENUM_VALUES.items():
            if field not in frontmatter:
                continue

            value = frontmatter[field]
            if value not in allowed_values:
                self.errors.append({
                    'file': str(file_path),
                    'message': f'Field {field} has invalid value: {value}. Allowed values: {allowed_values}'
                })

    def _validate_date_formats(self, file_path: Path, frontmatter: Dict, doc_type: str):
        """Validate date format (YYYY-MM-DD)"""
        date_fields = ['date', 'start_date', 'end_date', 'created_at', 'published_at']
        for field in date_fields:
            if field not in frontmatter:
                continue

            date_str = frontmatter[field]
            if not isinstance(date_str, str):
                continue

            try:
                datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                try:
                    datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except ValueError:
                    self.errors.append({
                        'file': str(file_path),
                        'message': f'Field {field} has invalid date format: {date_str}. Expected YYYY-MM-DD or ISO format'
                    })


def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(
        description="Validate Content Vault against specification"
    )
    parser.add_argument(
        "vault_path",
        type=str,
        nargs="?",
        default=None,
        help="Path to content vault (default: ~/content-vault)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
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

    validator = VaultValidator(vault_path)
    is_valid, errors, warnings = validator.validate_vault()

    if args.json:
        import json
        output = {
            'valid': is_valid,
            'errors': errors,
            'warnings': warnings,
            'error_count': len(errors),
            'warning_count': len(warnings)
        }
        print(json.dumps(output, indent=2))
    else:
        if is_valid:
            print("Vault validation passed!")
            if warnings:
                print(f"\nWARNING: {len(warnings)} warning(s):")
                for warning in warnings:
                    print(f"  - {warning['file']}: {warning['message']}")
        else:
            print(f"ERROR: Found {len(errors)} error(s):")
            for error in errors:
                print(f"  - {error['file']}: {error['message']}")
            if warnings:
                print(f"\nWARNING: {len(warnings)} warning(s):")
                for warning in warnings:
                    print(f"  - {warning['file']}: {warning['message']}")

    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()

