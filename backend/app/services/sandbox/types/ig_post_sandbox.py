"""
IG Post Sandbox implementation

Manages Instagram post projects with visual style analysis, format support,
and preview capabilities. Supports multiple IG formats (square, portrait, landscape, story, carousel).
"""

from typing import Optional, Dict, Any, List
import logging
import json

from backend.app.services.sandbox.base_sandbox import BaseSandbox

logger = logging.getLogger(__name__)

IG_POST_TEMPLATE = {
    "posts": [],
    "metadata": {
        "format": "square",
        "style_lens_id": None,
        "version": "1.0"
    }
}


class IGPostSandbox(BaseSandbox):
    """
    Sandbox for Instagram post projects

    Manages:
    - Post content (text, images, hashtags)
    - Visual style analysis and application
    - Multiple format support (square, portrait, landscape, story, carousel)
    - Preview and version management
    """

    def __init__(
        self,
        sandbox_id: str,
        sandbox_type: str,
        workspace_id: str,
        storage,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(sandbox_id, sandbox_type, workspace_id, storage, metadata)
        self.sandbox_type = "ig_post"

    async def initialize_template(self) -> bool:
        """
        Initialize IG Post project template.

        Creates initial post structure and metadata.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            template_path = "posts.json"
            if not await self.file_exists(template_path):
                await self.write_file(
                    template_path,
                    json.dumps(IG_POST_TEMPLATE, indent=2, ensure_ascii=False)
                )
                logger.info(f"Created IG Post template: {template_path}")

            logger.info(f"Initialized IG Post template for sandbox {self.sandbox_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize template: {e}")
            return False

    async def add_post(
        self,
        post_data: Dict[str, Any],
        format: str = "square"
    ) -> bool:
        """
        Add a new post to the sandbox.

        Args:
            post_data: Post data (text, images, hashtags, etc.)
            format: Post format (square, portrait, landscape, story, carousel)

        Returns:
            True if post added successfully, False otherwise
        """
        try:
            template_path = "posts.json"
            if await self.file_exists(template_path):
                content = await self.read_file(template_path)
                posts_data = json.loads(content)
            else:
                posts_data = IG_POST_TEMPLATE.copy()

            post_entry = {
                "id": f"post_{len(posts_data.get('posts', [])) + 1}",
                "format": format,
                "data": post_data,
                "created_at": self._get_timestamp()
            }

            posts_data.setdefault("posts", []).append(post_entry)
            posts_data["metadata"]["format"] = format

            await self.write_file(
                template_path,
                json.dumps(posts_data, indent=2, ensure_ascii=False)
            )

            logger.info(f"Added post to sandbox {self.sandbox_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to add post: {e}")
            return False

    async def apply_visual_lens(
        self,
        lens_data: Dict[str, Any]
    ) -> bool:
        """
        Apply Visual Lens rules to posts.

        Args:
            lens_data: IGVisualLensSchema data

        Returns:
            True if lens applied successfully, False otherwise
        """
        try:
            template_path = "posts.json"
            if await self.file_exists(template_path):
                content = await self.read_file(template_path)
                posts_data = json.loads(content)
            else:
                posts_data = IG_POST_TEMPLATE.copy()

            posts_data["metadata"]["style_lens_id"] = lens_data.get("lens_id")
            posts_data["metadata"]["visual_lens"] = lens_data

            await self.write_file(
                template_path,
                json.dumps(posts_data, indent=2, ensure_ascii=False)
            )

            logger.info(f"Applied visual lens {lens_data.get('lens_id')} to sandbox {self.sandbox_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to apply visual lens: {e}")
            return False

    async def get_posts(self) -> List[Dict[str, Any]]:
        """
        Get all posts from the sandbox.

        Returns:
            List of post entries
        """
        try:
            template_path = "posts.json"
            if await self.file_exists(template_path):
                content = await self.read_file(template_path)
                posts_data = json.loads(content)
                return posts_data.get("posts", [])
            return []

        except Exception as e:
            logger.error(f"Failed to get posts: {e}")
            return []

    async def get_change_summary(
        self,
        from_version: Optional[str],
        to_version: Optional[str]
    ) -> str:
        """Get AI-generated summary of changes between versions"""
        from_files = await self.list_files(version=from_version)
        to_files = await self.list_files(version=to_version)

        from_paths = {f["path"] for f in from_files}
        to_paths = {f["path"] for f in to_files}

        added = to_paths - from_paths
        removed = from_paths - to_paths
        modified = from_paths & to_paths

        summary_parts = []
        if added:
            summary_parts.append(f"Added {len(added)} file(s)")
        if removed:
            summary_parts.append(f"Removed {len(removed)} file(s)")
        if modified:
            summary_parts.append(f"Modified {len(modified)} file(s)")

        return "; ".join(summary_parts) if summary_parts else "No changes"

    async def validate(self) -> Dict[str, Any]:
        """Validate IG Post sandbox structure"""
        errors = []
        warnings = []

        files = await self.list_files()
        file_paths = {f["path"] for f in files}

        if "posts.json" not in file_paths:
            warnings.append("posts.json file not found")

        try:
            if "posts.json" in file_paths:
                content = await self.read_file("posts.json")
                posts_data = json.loads(content)
                posts = posts_data.get("posts", [])

                if not posts:
                    warnings.append("No posts found in posts.json")

                for post in posts:
                    if "data" not in post:
                        errors.append(f"Post {post.get('id', 'unknown')} missing data field")
                    if "format" not in post:
                        errors.append(f"Post {post.get('id', 'unknown')} missing format field")

        except json.JSONDecodeError:
            errors.append("posts.json is not valid JSON")
        except Exception as e:
            errors.append(f"Error validating posts.json: {str(e)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO format string."""
        from datetime import datetime
        return datetime.now().isoformat()





