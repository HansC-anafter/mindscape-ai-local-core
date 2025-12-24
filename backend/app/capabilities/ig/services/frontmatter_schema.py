"""
Unified Frontmatter Schema v2.0.0 (Authoritative Definition)

This module defines the authoritative Frontmatter Schema for all content types.
All tools and playbooks should use this schema as the single source of truth.
"""
from typing import Dict, Any, List, Optional, Literal
from enum import Enum


class Domain(str, Enum):
    """Content domain classification"""
    IG = "ig"
    WP = "wp"
    SEO = "seo"
    BOOK = "book"
    BRAND = "brand"
    OPS = "ops"
    BLOG = "blog"


class Intent(str, Enum):
    """Content intent"""
    EDUCATION = "education"
    CONVERSION = "conversion"
    BRAND = "brand"
    AWARENESS = "awareness"


class Status(str, Enum):
    """Content status"""
    DRAFT = "draft"
    REVIEW = "review"
    READY = "ready"
    EXPORTED = "exported"
    PUBLISHED = "published"


class SharePolicy(str, Enum):
    """Content share policy"""
    LOCAL_ONLY = "local_only"
    SYNC_OK = "sync_ok"
    PUBLISH_OK = "publish_ok"


class UnifiedFrontmatterSchema:
    """
    Unified Frontmatter Schema v2.0.0

    This is the authoritative schema definition for all content types.
    All tools and playbooks should reference this schema.
    """

    # Required fields (all content types)
    REQUIRED_FIELDS = {
        "workspace_id": str,
        "domain": Domain,
        "intent": Intent,
        "status": Status,
        "share_policy": SharePolicy
    }

    # Optional fields (all content types)
    OPTIONAL_FIELDS = {
        "series": Optional[str],
        "rev": Optional[str],
        "created_at": Optional[str],  # ISO 8601
        "updated_at": Optional[str],  # ISO 8601
        "published_at": Optional[str]  # ISO 8601
    }

    # Platform-specific fields (IG Post)
    IG_SPECIFIC_FIELDS = {
        "platform": Literal["instagram"],
        "type": Literal["post", "carousel", "reel", "story"],
        "ig_intent": Optional[List[str]],
        "cta_type": Optional[Literal["save", "comment", "dm", "link"]],
        "required_assets": Optional[List[str]],
        "risk_flags": Optional[List[str]],
        "hashtag_groups": Optional[List[str]],
        "metrics": Optional[Dict[str, Any]]
    }

    # Platform-specific fields (WordPress)
    WP_SPECIFIC_FIELDS = {
        "platform": Literal["wordpress"],
        "post_type": Optional[Literal["post", "page", "custom_post_type"]],
        "categories": Optional[List[str]],
        "tags": Optional[List[str]],
        "featured_image": Optional[str]
    }

    # Platform-specific fields (Book)
    BOOK_SPECIFIC_FIELDS = {
        "book": Optional[str],
        "type": Optional[Literal["intro", "structure", "chapter", "section"]],
        "year": Optional[int],
        "chapter": Optional[int],
        "section": Optional[int],
        "slug": Optional[str],
        "title": Optional[str],
        "description": Optional[str],
        "order": Optional[int],
        "tags": Optional[List[str]]
    }

    @classmethod
    def get_required_fields(cls) -> Dict[str, Any]:
        """Get required fields for all content types"""
        return cls.REQUIRED_FIELDS.copy()

    @classmethod
    def get_optional_fields(cls) -> Dict[str, Any]:
        """Get optional fields for all content types"""
        return cls.OPTIONAL_FIELDS.copy()

    @classmethod
    def get_platform_specific_fields(cls, domain: str) -> Dict[str, Any]:
        """Get platform-specific fields for given domain"""
        if domain == Domain.IG:
            return cls.IG_SPECIFIC_FIELDS.copy()
        elif domain == Domain.WP:
            return cls.WP_SPECIFIC_FIELDS.copy()
        elif domain == Domain.BOOK:
            return cls.BOOK_SPECIFIC_FIELDS.copy()
        else:
            return {}

    @classmethod
    def get_all_fields(cls, domain: str) -> Dict[str, Any]:
        """Get all fields (required + optional + platform-specific) for given domain"""
        all_fields = {}
        all_fields.update(cls.REQUIRED_FIELDS)
        all_fields.update(cls.OPTIONAL_FIELDS)
        all_fields.update(cls.get_platform_specific_fields(domain))
        return all_fields

    @classmethod
    def validate_domain(cls, domain: str) -> bool:
        """Validate domain value"""
        try:
            Domain(domain)
            return True
        except ValueError:
            return False

    @classmethod
    def validate_intent(cls, intent: str) -> bool:
        """Validate intent value"""
        try:
            Intent(intent)
            return True
        except ValueError:
            return False

    @classmethod
    def validate_status(cls, status: str) -> bool:
        """Validate status value"""
        try:
            Status(status)
            return True
        except ValueError:
            return False

    @classmethod
    def validate_share_policy(cls, share_policy: str) -> bool:
        """Validate share_policy value"""
        try:
            SharePolicy(share_policy)
            return True
        except ValueError:
            return False

