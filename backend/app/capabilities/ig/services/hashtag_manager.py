"""
Hashtag Manager for IG Post

Manages hashtag groups (brand fixed, theme, campaign) and combines hashtags
based on intent, audience, and region.
"""
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class HashtagManager:
    """
    Manages hashtag groups and combinations for IG Post

    Supports:
    - Hashtag group management (brand fixed, theme, campaign)
    - Hashtag combination based on intent, audience, region
    - Blocked hashtag checking
    - Recommendation based on historical data
    """

    def __init__(self, hashtag_config_path: Optional[str] = None):
        """
        Initialize Hashtag Manager

        Args:
            hashtag_config_path: Path to hashtag configuration file (JSON)
        """
        if hashtag_config_path:
            self.config_path = Path(hashtag_config_path)
        else:
            # Use default config path
            current_file = Path(__file__)
            self.config_path = current_file.parent / "hashtag_config.json"

        self.hashtag_groups = self._load_hashtag_groups()
        self.blocked_hashtags = self._load_blocked_hashtags()

    def _load_hashtag_groups(self) -> Dict[str, Any]:
        """Load hashtag groups from config file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("hashtag_groups", {})
            except Exception as e:
                logger.warning(f"Failed to load hashtag config: {e}")

        # Return default hashtag groups
        return self._get_default_hashtag_groups()

    def _load_blocked_hashtags(self) -> List[str]:
        """Load blocked hashtags from config file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("blocked_hashtags", [])
            except Exception as e:
                logger.warning(f"Failed to load hashtag config: {e}")

        return []

    def _get_default_hashtag_groups(self) -> Dict[str, Any]:
        """Get default hashtag groups structure"""
        return {
            "brand_fixed": {
                "name": "品牌固定組",
                "hashtags": ["#mindscape", "#mindscapeai", "#aiassistant"],
                "required": True,
                "count": 3
            },
            "theme_yoga": {
                "name": "主題組 - 瑜伽",
                "hashtags": ["#yoga", "#yogalife", "#yogapractice", "#mindfulness", "#wellness"],
                "required": False,
                "count": 5
            },
            "theme_coffee": {
                "name": "主題組 - 咖啡",
                "hashtags": ["#coffee", "#coffeelover", "#coffeetime", "#coffeebreak", "#coffeeculture"],
                "required": False,
                "count": 5
            },
            "campaign_week_50": {
                "name": "活動組 - 第50週",
                "hashtags": ["#week50", "#campaign", "#special"],
                "required": False,
                "count": 3
            }
        }

    def load_groups(self) -> Dict[str, Any]:
        """
        Load all hashtag groups

        Returns:
            Dictionary of hashtag groups
        """
        return self.hashtag_groups.copy()

    def combine_hashtags(
        self,
        intent: str,
        audience: Optional[str] = None,
        region: Optional[str] = None,
        hashtag_count: int = 25,
        hashtag_groups: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Combine hashtags based on intent, audience, and region

        Args:
            intent: Post intent (教育, 引流, 轉換, 品牌)
            audience: Target audience (optional)
            region: Region (optional)
            hashtag_count: Required hashtag count (15, 25, or 30)
            hashtag_groups: Hashtag groups to use (if None, use loaded groups)

        Returns:
            {
                "recommended_hashtags": List[str],
                "blocked_hashtags": List[str],
                "hashtag_groups_used": List[str]
            }
        """
        if hashtag_groups is None:
            hashtag_groups = self.hashtag_groups

        recommended_hashtags = []
        blocked_hashtags = []
        hashtag_groups_used = []

        # Always include brand fixed group
        if "brand_fixed" in hashtag_groups:
            brand_hashtags = hashtag_groups["brand_fixed"]["hashtags"]
            recommended_hashtags.extend(brand_hashtags)
            hashtag_groups_used.append("brand_fixed")

        # Select theme groups based on intent
        theme_groups = self._select_theme_groups(intent, hashtag_groups)
        for group_name, group_data in theme_groups.items():
            if group_name not in hashtag_groups_used:
                recommended_hashtags.extend(group_data["hashtags"][:group_data.get("count", 5)])
                hashtag_groups_used.append(group_name)

        # Add campaign groups if available
        campaign_groups = {k: v for k, v in hashtag_groups.items() if k.startswith("campaign_")}
        for group_name, group_data in campaign_groups.items():
            if len(recommended_hashtags) < hashtag_count and group_name not in hashtag_groups_used:
                recommended_hashtags.extend(group_data["hashtags"][:group_data.get("count", 3)])
                hashtag_groups_used.append(group_name)

        # Check for blocked hashtags
        for hashtag in recommended_hashtags:
            if self._is_blocked(hashtag):
                blocked_hashtags.append(hashtag)
                recommended_hashtags.remove(hashtag)

        # Fill to required count with generic hashtags
        while len(recommended_hashtags) < hashtag_count:
            generic_hashtag = self._generate_generic_hashtag(intent, audience, region)
            if generic_hashtag and not self._is_blocked(generic_hashtag):
                if generic_hashtag not in recommended_hashtags:
                    recommended_hashtags.append(generic_hashtag)
            else:
                break

        # Trim to required count
        recommended_hashtags = recommended_hashtags[:hashtag_count]

        return {
            "recommended_hashtags": recommended_hashtags,
            "blocked_hashtags": blocked_hashtags,
            "hashtag_groups_used": hashtag_groups_used,
            "total_count": len(recommended_hashtags)
        }

    def _select_theme_groups(self, intent: str, hashtag_groups: Dict[str, Any]) -> Dict[str, Any]:
        """Select theme groups based on intent"""
        theme_groups = {k: v for k, v in hashtag_groups.items() if k.startswith("theme_")}

        # Simple selection logic (can be enhanced with LLM)
        selected = {}

        if intent == "教育":
            # Select educational themes
            for name, data in theme_groups.items():
                if "education" in name.lower() or "learn" in name.lower():
                    selected[name] = data
        elif intent == "引流":
            # Select engagement themes
            for name, data in theme_groups.items():
                if "engagement" in name.lower() or "community" in name.lower():
                    selected[name] = data
        elif intent == "轉換":
            # Select conversion themes
            for name, data in theme_groups.items():
                if "conversion" in name.lower() or "sales" in name.lower():
                    selected[name] = data
        elif intent == "品牌":
            # Select brand themes
            for name, data in theme_groups.items():
                if "brand" in name.lower() or "awareness" in name.lower():
                    selected[name] = data

        # If no specific match, select first theme group
        if not selected and theme_groups:
            first_key = next(iter(theme_groups))
            selected[first_key] = theme_groups[first_key]

        return selected

    def _is_blocked(self, hashtag: str) -> bool:
        """Check if hashtag is blocked"""
        # Normalize hashtag (remove # if present)
        normalized = hashtag.lstrip("#").lower()
        return normalized in [h.lstrip("#").lower() for h in self.blocked_hashtags]

    def _generate_generic_hashtag(
        self,
        intent: str,
        audience: Optional[str] = None,
        region: Optional[str] = None
    ) -> Optional[str]:
        """Generate generic hashtag based on intent, audience, region"""
        # Simple generic hashtag generation (can be enhanced with LLM)
        generic_hashtags = {
            "教育": ["#learn", "#education", "#knowledge", "#tips", "#howto"],
            "引流": ["#follow", "#like", "#share", "#comment", "#engagement"],
            "轉換": ["#sale", "#offer", "#discount", "#promo", "#deal"],
            "品牌": ["#brand", "#awareness", "#community", "#lifestyle", "#inspiration"]
        }

        base_hashtags = generic_hashtags.get(intent, ["#instagram", "#post", "#content"])

        # Return first available (simple implementation)
        return base_hashtags[0] if base_hashtags else None

    def check_blocked(self, hashtags: List[str]) -> Dict[str, Any]:
        """
        Check if any hashtags are blocked

        Args:
            hashtags: List of hashtags to check

        Returns:
            {
                "blocked_hashtags": List[str],
                "allowed_hashtags": List[str]
            }
        """
        blocked = []
        allowed = []

        for hashtag in hashtags:
            if self._is_blocked(hashtag):
                blocked.append(hashtag)
            else:
                allowed.append(hashtag)

        return {
            "blocked_hashtags": blocked,
            "allowed_hashtags": allowed,
            "blocked_count": len(blocked),
            "allowed_count": len(allowed)
        }





