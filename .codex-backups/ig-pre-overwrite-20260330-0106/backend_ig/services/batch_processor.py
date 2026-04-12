"""
Batch Processor System for IG Post

Manages batch processing of multiple posts including validation,
generation, and export operations.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from capabilities.ig.services.workspace_storage import WorkspaceStorage
from capabilities.ig.services.review_system import ReviewSystem
from capabilities.ig.services.export_pack_generator import ExportPackGenerator

logger = logging.getLogger(__name__)


class BatchProcessor:
    """
    Manages batch processing of multiple IG posts

    Supports:
    - Batch validation
    - Batch generation
    - Batch export
    - Progress tracking
    """

    def __init__(self, workspace_storage: WorkspaceStorage):
        """
        Initialize Batch Processor System

        Args:
            workspace_storage: WorkspaceStorage instance
        """
        self.storage = workspace_storage
        self.review_system = ReviewSystem(workspace_storage)

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

    def batch_validate(
        self,
        post_paths: List[str],
        strict_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Batch validate multiple posts

        Args:
            post_paths: List of post file paths (relative to workspace or Obsidian-style)
            strict_mode: If True, all required fields must be present

        Returns:
            Batch validation results
        """
        results = []
        total_posts = len(post_paths)
        passed_count = 0
        failed_count = 0

        for post_path in post_paths:
            full_path = self._resolve_post_path(post_path)

            if not full_path.exists():
                results.append({
                    "post_path": post_path,
                    "status": "error",
                    "error": "File not found"
                })
                failed_count += 1
                continue

            try:
                # Use ReviewSystem to read markdown file
                frontmatter, content = self.review_system._read_markdown_file(full_path)

                # Import FrontmatterValidator
                from capabilities.ig.services.frontmatter_validator import FrontmatterValidator

                validator = FrontmatterValidator(strict_mode=strict_mode)
                validation_result = validator.validate(frontmatter, domain=None)
                is_valid = validation_result.get("is_valid", False)
                readiness_score = validation_result.get("readiness_score", 0)
                missing_fields = validation_result.get("missing_fields", [])
                warnings = validation_result.get("warnings", [])

                results.append({
                    "post_path": post_path,
                    "status": "passed" if is_valid else "failed",
                    "readiness_score": readiness_score,
                    "missing_fields": missing_fields,
                    "warnings": warnings
                })

                if is_valid:
                    passed_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(f"Error validating {post_path}: {e}", exc_info=True)
                results.append({
                    "post_path": post_path,
                    "status": "error",
                    "error": str(e)
                })
                failed_count += 1

        return {
            "total_posts": total_posts,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "results": results,
            "processed_at": datetime.now().isoformat()
        }

    def batch_generate_export_packs(
        self,
        post_paths: List[str],
        output_folder: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Batch generate export packs for multiple posts

        Args:
            post_paths: List of post file paths (relative to workspace or Obsidian-style)
            output_folder: Output folder for export packs (optional)

        Returns:
            Batch generation results
        """
        results = []
        total_posts = len(post_paths)
        success_count = 0
        failed_count = 0

        for post_path in post_paths:
            full_path = self._resolve_post_path(post_path)

            if not full_path.exists():
                results.append({
                    "post_path": post_path,
                    "status": "error",
                    "error": "File not found"
                })
                failed_count += 1
                continue

            try:
                # Read post content and frontmatter
                frontmatter, content = self.review_system._read_markdown_file(full_path)

                # Generate export pack
                generator = ExportPackGenerator(self.storage)
                export_result = generator.generate_export_pack(
                    post_path=post_path,
                    post_content=content,
                    frontmatter=frontmatter,
                    output_folder=output_folder
                )

                results.append({
                    "post_path": post_path,
                    "status": "success",
                    "export_pack_path": export_result.get("export_pack_path"),
                    "files_generated": export_result.get("files_generated", [])
                })
                success_count += 1

            except Exception as e:
                logger.error(f"Error generating export pack for {post_path}: {e}", exc_info=True)
                results.append({
                    "post_path": post_path,
                    "status": "error",
                    "error": str(e)
                })
                failed_count += 1

        return {
            "total_posts": total_posts,
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
            "processed_at": datetime.now().isoformat()
        }

    def batch_update_status(
        self,
        post_paths: List[str],
        new_status: str
    ) -> Dict[str, Any]:
        """
        Batch update status for multiple posts

        Args:
            post_paths: List of post file paths (relative to workspace or Obsidian-style)
            new_status: New status to set

        Returns:
            Batch update results
        """
        results = []
        total_posts = len(post_paths)
        success_count = 0
        failed_count = 0

        for post_path in post_paths:
            full_path = self._resolve_post_path(post_path)

            if not full_path.exists():
                results.append({
                    "post_path": post_path,
                    "status": "error",
                    "error": "File not found"
                })
                failed_count += 1
                continue

            try:
                frontmatter, content = self.review_system._read_markdown_file(full_path)

                frontmatter["status"] = new_status
                frontmatter["updated_at"] = datetime.now().isoformat()

                self.review_system._write_markdown_file(full_path, frontmatter, content)

                results.append({
                    "post_path": post_path,
                    "status": "success",
                    "new_status": new_status
                })
                success_count += 1

            except Exception as e:
                logger.error(f"Error updating status for {post_path}: {e}", exc_info=True)
                results.append({
                    "post_path": post_path,
                    "status": "error",
                    "error": str(e)
                })
                failed_count += 1

        return {
            "total_posts": total_posts,
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
            "processed_at": datetime.now().isoformat()
        }

    def batch_process(
        self,
        post_paths: List[str],
        operations: List[str],
        operation_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Batch process multiple posts with specified operations

        Args:
            post_paths: List of post file paths (relative to workspace or Obsidian-style)
            operations: List of operations to perform (e.g., ["validate", "generate_export_pack"])
            operation_config: Configuration for operations (optional)

        Returns:
            Batch processing results
        """
        config = operation_config or {}
        all_results = {}

        if "validate" in operations:
            all_results["validation"] = self.batch_validate(
                post_paths=post_paths,
                strict_mode=config.get("strict_mode", False)
            )

        if "generate_export_pack" in operations:
            all_results["export_packs"] = self.batch_generate_export_packs(
                post_paths=post_paths,
                output_folder=config.get("output_folder")
            )

        if "update_status" in operations:
            all_results["status_updates"] = self.batch_update_status(
                post_paths=post_paths,
                new_status=config.get("new_status", "ready")
            )

        return {
            "total_posts": len(post_paths),
            "operations": operations,
            "results": all_results,
            "processed_at": datetime.now().isoformat()
        }

