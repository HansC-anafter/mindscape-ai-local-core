"""
Frontmatter Schema Validator

Validates frontmatter against Unified Frontmatter Schema v2.0.0
and calculates Readiness Score for content.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.app.services.ig_obsidian.frontmatter_schema import (
    UnifiedFrontmatterSchema,
    Domain,
    Intent,
    Status,
    SharePolicy
)

logger = logging.getLogger(__name__)


class FrontmatterValidator:
    """
    Validates frontmatter against Unified Frontmatter Schema v2.0.0

    Supports:
    - Unified field validation (workspace_id, domain, intent, status, share_policy)
    - Platform-specific field validation (IG, WordPress, Book, etc.)
    - Readiness Score calculation
    - Migration detection (v1.0 -> v2.0)
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize validator

        Args:
            strict_mode: If True, all required fields must be present
        """
        self.strict_mode = strict_mode
        self.schema = UnifiedFrontmatterSchema()

    def validate(self, frontmatter: Dict[str, Any], domain: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate frontmatter against schema

        Args:
            frontmatter: Frontmatter dictionary to validate
            domain: Expected domain (if None, will use frontmatter['domain'])

        Returns:
            {
                "is_valid": bool,
                "readiness_score": int (0-100),
                "missing_fields": List[str],
                "warnings": List[str],
                "errors": List[str]
            }
        """
        errors = []
        warnings = []
        missing_fields = []

        # Check for v1.0 schema migration
        if "content_type" in frontmatter:
            warnings.append("Detected v1.0 schema (content_type), please migrate to v2.0")

        # Determine domain
        if domain is None:
            domain = frontmatter.get("domain")

        if not domain:
            errors.append("domain field is required")
            return self._build_result(False, 0, missing_fields, warnings, errors)

        # Validate domain
        if not self.schema.validate_domain(domain):
            errors.append(f"Invalid domain: {domain}")
            return self._build_result(False, 0, missing_fields, warnings, errors)

        # Validate required fields
        required_fields = self.schema.get_required_fields()
        for field_name, field_type in required_fields.items():
            if field_name not in frontmatter:
                missing_fields.append(field_name)
                if self.strict_mode:
                    errors.append(f"Required field missing: {field_name}")

        # Validate field values
        if "intent" in frontmatter and not self.schema.validate_intent(frontmatter["intent"]):
            errors.append(f"Invalid intent: {frontmatter['intent']}")

        if "status" in frontmatter and not self.schema.validate_status(frontmatter["status"]):
            errors.append(f"Invalid status: {frontmatter['status']}")

        if "share_policy" in frontmatter and not self.schema.validate_share_policy(frontmatter["share_policy"]):
            errors.append(f"Invalid share_policy: {frontmatter['share_policy']}")

        # Validate platform-specific fields
        platform_fields = self.schema.get_platform_specific_fields(domain)
        if domain == Domain.IG:
            if "platform" in frontmatter and frontmatter["platform"] != "instagram":
                errors.append("IG Post must have platform='instagram'")
            if "type" in frontmatter and frontmatter["type"] not in ["post", "carousel", "reel", "story"]:
                errors.append(f"Invalid IG type: {frontmatter['type']}")

        # Calculate Readiness Score
        readiness_score = self._calculate_readiness_score(frontmatter, domain, missing_fields)

        is_valid = len(errors) == 0 and (not self.strict_mode or len(missing_fields) == 0)

        return self._build_result(is_valid, readiness_score, missing_fields, warnings, errors)

    def _calculate_readiness_score(
        self,
        frontmatter: Dict[str, Any],
        domain: str,
        missing_fields: List[str]
    ) -> int:
        """
        Calculate Readiness Score (0-100)

        Scoring:
        - Base score: 30 (required fields complete)
        - Content complete: +20 (has content)
        - Assets complete: +20 (required_assets all exist) - IG only
        - Hashtag complete: +15 (has hashtag_groups) - IG only
        - CTA clear: +10 (has cta_type) - IG only
        - Series linked: +5 (has series)
        """
        score = 0

        # Base score: required fields complete
        required_fields = self.schema.get_required_fields()
        missing_required = [f for f in missing_fields if f in required_fields]
        if len(missing_required) == 0:
            score += 30

        # Content complete (assumed if frontmatter exists)
        score += 20

        # Platform-specific scoring (IG Post)
        if domain == Domain.IG:
            # Assets complete
            required_assets = frontmatter.get("required_assets", [])
            if required_assets and len(required_assets) > 0:
                score += 20

            # Hashtag complete
            hashtag_groups = frontmatter.get("hashtag_groups", [])
            if hashtag_groups and len(hashtag_groups) > 0:
                score += 15

            # CTA clear
            if frontmatter.get("cta_type"):
                score += 10

        # Series linked
        if frontmatter.get("series"):
            score += 5

        return min(score, 100)

    def _build_result(
        self,
        is_valid: bool,
        readiness_score: int,
        missing_fields: List[str],
        warnings: List[str],
        errors: List[str]
    ) -> Dict[str, Any]:
        """Build validation result dictionary"""
        return {
            "is_valid": is_valid,
            "readiness_score": readiness_score,
            "missing_fields": missing_fields,
            "warnings": warnings,
            "errors": errors
        }


