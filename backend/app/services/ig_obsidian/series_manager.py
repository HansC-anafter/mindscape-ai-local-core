"""
Series Manager for IG Post

Manages post series including creation, updates, querying, and cross-referencing.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class SeriesManager:
    """
    Manages IG Post series

    Supports:
    - Series creation and updates
    - Series querying
    - Cross-referencing between posts in series
    - Progress tracking
    """

    def __init__(self, vault_path: str):
        """
        Initialize Series Manager

        Args:
            vault_path: Path to Obsidian Vault
        """
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.series_index_path = self.vault_path / ".obsidian" / "series_index.json"

    def create_series(
        self,
        series_code: str,
        series_name: str,
        description: Optional[str] = None,
        total_posts: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new series

        Args:
            series_code: Series code (unique identifier)
            series_name: Series name
            description: Series description (optional)
            total_posts: Total number of posts planned (optional)

        Returns:
            Series information dictionary
        """
        series_index = self._load_series_index()

        if series_code in series_index:
            raise ValueError(f"Series {series_code} already exists")

        series = {
            "series_code": series_code,
            "series_name": series_name,
            "description": description,
            "total_posts": total_posts,
            "current_post": 0,
            "posts": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        series_index[series_code] = series
        self._save_series_index(series_index)

        return series

    def add_post_to_series(
        self,
        series_code: str,
        post_path: str,
        post_slug: str,
        post_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Add post to series

        Args:
            series_code: Series code
            post_path: Post file path (relative to vault)
            post_slug: Post slug
            post_number: Post number in series (optional, auto-increment if not provided)

        Returns:
            Updated series information
        """
        series_index = self._load_series_index()

        if series_code not in series_index:
            raise ValueError(f"Series {series_code} does not exist")

        series = series_index[series_code]

        # Auto-increment post number if not provided
        if post_number is None:
            post_number = series["current_post"] + 1

        post_info = {
            "post_path": post_path,
            "post_slug": post_slug,
            "post_number": post_number,
            "added_at": datetime.now().isoformat()
        }

        series["posts"].append(post_info)
        series["current_post"] = post_number
        series["updated_at"] = datetime.now().isoformat()

        # Sort posts by post_number
        series["posts"].sort(key=lambda x: x["post_number"])

        series_index[series_code] = series
        self._save_series_index(series_index)

        return series

    def get_series(self, series_code: str) -> Optional[Dict[str, Any]]:
        """
        Get series information

        Args:
            series_code: Series code

        Returns:
            Series information dictionary or None if not found
        """
        series_index = self._load_series_index()
        return series_index.get(series_code)

    def list_series(self) -> List[Dict[str, Any]]:
        """
        List all series

        Returns:
            List of series information dictionaries
        """
        series_index = self._load_series_index()
        return list(series_index.values())

    def get_series_posts(self, series_code: str) -> List[Dict[str, Any]]:
        """
        Get all posts in a series

        Args:
            series_code: Series code

        Returns:
            List of post information dictionaries
        """
        series = self.get_series(series_code)
        if not series:
            return []

        return series.get("posts", [])

    def get_previous_next_posts(
        self,
        series_code: str,
        current_post_number: int
    ) -> Dict[str, Any]:
        """
        Get previous and next posts in series

        Args:
            series_code: Series code
            current_post_number: Current post number

        Returns:
            {
                "previous": Optional[Dict],
                "next": Optional[Dict]
            }
        """
        posts = self.get_series_posts(series_code)

        previous = None
        next_post = None

        for i, post in enumerate(posts):
            if post["post_number"] == current_post_number:
                if i > 0:
                    previous = posts[i - 1]
                if i < len(posts) - 1:
                    next_post = posts[i + 1]
                break

        return {
            "previous": previous,
            "next": next_post
        }

    def update_series_progress(self, series_code: str) -> Dict[str, Any]:
        """
        Update series progress

        Args:
            series_code: Series code

        Returns:
            Updated series with progress information
        """
        series = self.get_series(series_code)
        if not series:
            raise ValueError(f"Series {series_code} does not exist")

        total_posts = series.get("total_posts")
        current_count = len(series.get("posts", []))

        progress = {
            "current_count": current_count,
            "total_posts": total_posts,
            "progress_percentage": (
                (current_count / total_posts * 100) if total_posts else None
            ),
            "is_complete": (
                current_count >= total_posts if total_posts else False
            )
        }

        series["progress"] = progress
        series["updated_at"] = datetime.now().isoformat()

        series_index = self._load_series_index()
        series_index[series_code] = series
        self._save_series_index(series_index)

        return series

    def _load_series_index(self) -> Dict[str, Any]:
        """Load series index from file"""
        if self.series_index_path.exists():
            try:
                with open(self.series_index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load series index: {e}")

        return {}

    def _save_series_index(self, series_index: Dict[str, Any]) -> None:
        """Save series index to file"""
        self.series_index_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.series_index_path, "w", encoding="utf-8") as f:
                json.dump(series_index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save series index: {e}")
            raise


