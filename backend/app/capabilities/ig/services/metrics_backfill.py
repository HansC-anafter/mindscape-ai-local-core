"""
Metrics Backfill System for IG Post

Manages post-publication metrics including manual backfill,
data analysis, and performance element tracking.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import yaml
import re

from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class MetricsBackfill:
    """
    Manages post-publication metrics backfill

    Supports:
    - Manual metrics backfill
    - Data analysis and rule writing
    - Performance element tracking
    - Metrics aggregation
    """

    def __init__(self, workspace_storage: WorkspaceStorage):
        """
        Initialize Metrics Backfill System

        Args:
            workspace_storage: WorkspaceStorage instance
        """
        self.storage = workspace_storage

    def _resolve_post_path(self, post_path: str) -> Path:
        """
        Resolve post_path to actual file path

        Args:
            post_path: Post path (may be Obsidian-style or new format)

        Returns:
            Resolved Path object
        """
        # Handle Obsidian-style paths (e.g., "20-Posts/2025-12-23_post-slug/post.md")
        # or new format (e.g., "post-slug/post.md")
        if post_path.startswith("20-Posts/") or post_path.startswith("posts/"):
            parts = post_path.split("/")
            if len(parts) >= 2:
                post_folder = parts[-2]
                post_file = parts[-1] if parts[-1].endswith(".md") else "post.md"
            else:
                post_folder = parts[0].replace(".md", "")
                post_file = "post.md"
        else:
            # Assume it's a post slug or folder name
            post_folder = post_path.replace(".md", "").replace("/", "")
            post_file = "post.md"

        # Extract post slug from folder name (format: YYYY-MM-DD_post-slug or post-slug)
        if "_" in post_folder:
            post_slug = post_folder.split("_")[-1]
        else:
            post_slug = post_folder

        # Get post path from storage
        post_dir = self.storage.get_post_path(post_slug)
        return post_dir / post_file

    def backfill_metrics(
        self,
        post_path: str,
        metrics: Dict[str, Any],
        backfill_source: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Backfill metrics to post frontmatter

        Args:
            post_path: Path to post file (relative to workspace or Obsidian-style)
            metrics: Metrics dictionary (e.g., reach_24h, engagement_24h, saves_24h, follows_24h)
            backfill_source: Source of backfill (e.g., "manual", "api", "scraper")

        Returns:
            Updated frontmatter with metrics
        """
        full_path = self._resolve_post_path(post_path)

        if not full_path.exists():
            raise FileNotFoundError(f"Post file not found: {post_path}")

        frontmatter, content = self._read_markdown_file(full_path)

        if "metrics" not in frontmatter:
            frontmatter["metrics"] = {}

        frontmatter["metrics"].update(metrics)

        if backfill_source:
            frontmatter["metrics"]["backfill_source"] = backfill_source
            frontmatter["metrics"]["backfilled_at"] = datetime.now().isoformat()

        frontmatter["updated_at"] = datetime.now().isoformat()

        self._write_markdown_file(full_path, frontmatter, content)

        return frontmatter

    def analyze_performance(
        self,
        post_path: str,
        threshold_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze post performance and generate insights

        Args:
            post_path: Path to post file (relative to workspace or Obsidian-style)
            threshold_config: Custom threshold configuration (optional)

        Returns:
            Performance analysis results
        """
        full_path = self._resolve_post_path(post_path)

        if not full_path.exists():
            raise FileNotFoundError(f"Post file not found: {post_path}")

        frontmatter, _ = self._read_markdown_file(full_path)

        metrics = frontmatter.get("metrics", {})

        if not metrics:
            return {
                "has_metrics": False,
                "message": "No metrics found for analysis"
            }

        reach_24h = metrics.get("reach_24h", 0)
        engagement_24h = metrics.get("engagement_24h", 0)
        saves_24h = metrics.get("saves_24h", 0)
        follows_24h = metrics.get("follows_24h", 0)

        default_thresholds = {
            "high_reach": 1000,
            "high_engagement": 100,
            "high_saves": 50,
            "high_follows": 10
        }

        thresholds = threshold_config or default_thresholds

        engagement_rate = (
            (engagement_24h / reach_24h * 100) if reach_24h > 0 else 0
        )

        save_rate = (
            (saves_24h / reach_24h * 100) if reach_24h > 0 else 0
        )

        follow_rate = (
            (follows_24h / reach_24h * 100) if reach_24h > 0 else 0
        )

        analysis = {
            "has_metrics": True,
            "metrics": {
                "reach_24h": reach_24h,
                "engagement_24h": engagement_24h,
                "saves_24h": saves_24h,
                "follows_24h": follows_24h
            },
            "rates": {
                "engagement_rate": round(engagement_rate, 2),
                "save_rate": round(save_rate, 2),
                "follow_rate": round(follow_rate, 2)
            },
            "performance_flags": {
                "high_reach": reach_24h >= thresholds["high_reach"],
                "high_engagement": engagement_24h >= thresholds["high_engagement"],
                "high_saves": saves_24h >= thresholds["high_saves"],
                "high_follows": follows_24h >= thresholds["high_follows"]
            },
            "overall_performance": self._calculate_overall_performance(
                reach_24h, engagement_24h, saves_24h, follows_24h, thresholds
            )
        }

        return analysis

    def track_performance_elements(
        self,
        post_path: str,
        elements: List[str],
        performance_level: str = "good"
    ) -> Dict[str, Any]:
        """
        Track performance elements that contributed to good/bad performance

        Args:
            post_path: Path to post file (relative to workspace or Obsidian-style)
            elements: List of performance elements (e.g., ["hashtag_strategy", "cta_type", "visual_style"])
            performance_level: Performance level ("good", "average", "poor")

        Returns:
            Updated frontmatter with performance elements
        """
        full_path = self._resolve_post_path(post_path)

        if not full_path.exists():
            raise FileNotFoundError(f"Post file not found: {post_path}")

        frontmatter, content = self._read_markdown_file(full_path)

        if "performance_elements" not in frontmatter:
            frontmatter["performance_elements"] = []

        element_entry = {
            "elements": elements,
            "performance_level": performance_level,
            "tracked_at": datetime.now().isoformat()
        }

        frontmatter["performance_elements"].append(element_entry)
        frontmatter["updated_at"] = datetime.now().isoformat()

        self._write_markdown_file(full_path, frontmatter, content)

        return frontmatter

    def write_performance_rules(
        self,
        post_path: str,
        rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Write performance rules based on analysis

        Args:
            post_path: Path to post file (relative to workspace or Obsidian-style)
            rules: List of performance rules (e.g., [{"condition": "...", "recommendation": "..."}])

        Returns:
            Updated frontmatter with performance rules
        """
        full_path = self._resolve_post_path(post_path)

        if not full_path.exists():
            raise FileNotFoundError(f"Post file not found: {post_path}")

        frontmatter, content = self._read_markdown_file(full_path)

        if "performance_rules" not in frontmatter:
            frontmatter["performance_rules"] = []

        for rule in rules:
            rule["created_at"] = datetime.now().isoformat()
            frontmatter["performance_rules"].append(rule)

        frontmatter["updated_at"] = datetime.now().isoformat()

        self._write_markdown_file(full_path, frontmatter, content)

        return frontmatter

    def aggregate_series_metrics(
        self,
        series_code: str,
        series_posts: List[str]
    ) -> Dict[str, Any]:
        """
        Aggregate metrics across a series of posts

        Args:
            series_code: Series code
            series_posts: List of post paths in the series

        Returns:
            Aggregated metrics summary
        """
        total_reach = 0
        total_engagement = 0
        total_saves = 0
        total_follows = 0
        posts_with_metrics = 0

        for post_path in series_posts:
            full_path = self._resolve_post_path(post_path)
            if not full_path.exists():
                continue

            frontmatter, _ = self._read_markdown_file(full_path)
            metrics = frontmatter.get("metrics", {})

            if metrics:
                total_reach += metrics.get("reach_24h", 0)
                total_engagement += metrics.get("engagement_24h", 0)
                total_saves += metrics.get("saves_24h", 0)
                total_follows += metrics.get("follows_24h", 0)
                posts_with_metrics += 1

        avg_reach = total_reach / posts_with_metrics if posts_with_metrics > 0 else 0
        avg_engagement = total_engagement / posts_with_metrics if posts_with_metrics > 0 else 0
        avg_saves = total_saves / posts_with_metrics if posts_with_metrics > 0 else 0
        avg_follows = total_follows / posts_with_metrics if posts_with_metrics > 0 else 0

        return {
            "series_code": series_code,
            "total_posts": len(series_posts),
            "posts_with_metrics": posts_with_metrics,
            "aggregated_metrics": {
                "total_reach": total_reach,
                "total_engagement": total_engagement,
                "total_saves": total_saves,
                "total_follows": total_follows
            },
            "average_metrics": {
                "avg_reach": round(avg_reach, 2),
                "avg_engagement": round(avg_engagement, 2),
                "avg_saves": round(avg_saves, 2),
                "avg_follows": round(avg_follows, 2)
            }
        }

    def _calculate_overall_performance(
        self,
        reach: int,
        engagement: int,
        saves: int,
        follows: int,
        thresholds: Dict[str, Any]
    ) -> str:
        """Calculate overall performance level"""
        score = 0

        if reach >= thresholds["high_reach"]:
            score += 1
        if engagement >= thresholds["high_engagement"]:
            score += 1
        if saves >= thresholds["high_saves"]:
            score += 1
        if follows >= thresholds["high_follows"]:
            score += 1

        if score >= 3:
            return "excellent"
        elif score >= 2:
            return "good"
        elif score >= 1:
            return "average"
        else:
            return "poor"

    def _read_markdown_file(self, file_path: Path) -> tuple[Dict[str, Any], str]:
        """Read markdown file and parse frontmatter"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter_match = re.match(
                r"^---\n(.*?)\n---\n(.*)$",
                content,
                re.DOTALL
            )

            if frontmatter_match:
                frontmatter_str = frontmatter_match.group(1)
                body = frontmatter_match.group(2)
                frontmatter = yaml.safe_load(frontmatter_str) or {}
            else:
                frontmatter = {}
                body = content

            return frontmatter, body

        except Exception as e:
            logger.error(f"Failed to read markdown file {file_path}: {e}", exc_info=True)
            raise

    def _write_markdown_file(
        self,
        file_path: Path,
        frontmatter: Dict[str, Any],
        content: str
    ) -> None:
        """Write markdown file with frontmatter"""
        try:
            frontmatter_str = yaml.dump(
                frontmatter,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            )

            full_content = f"---\n{frontmatter_str}---\n{content}"

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(full_content)

        except Exception as e:
            logger.error(f"Failed to write markdown file {file_path}: {e}", exc_info=True)
            raise

