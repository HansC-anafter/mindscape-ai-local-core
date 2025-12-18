"""
Batch Processor System for IG Post

Manages batch processing of multiple posts including validation,
generation, and export operations.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

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

    def __init__(self, vault_path: str):
        """
        Initialize Batch Processor System

        Args:
            vault_path: Path to Obsidian Vault
        """
        self.vault_path = Path(vault_path).expanduser().resolve()

    def batch_validate(
        self,
        post_paths: List[str],
        strict_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Batch validate multiple posts

        Args:
            post_paths: List of post file paths (relative to vault)
            strict_mode: If True, all required fields must be present

        Returns:
            Batch validation results
        """
        results = []
        total_posts = len(post_paths)
        passed_count = 0
        failed_count = 0

        for post_path in post_paths:
            full_path = self.vault_path / post_path

            if not full_path.exists():
                results.append({
                    "post_path": post_path,
                    "status": "error",
                    "error": "File not found"
                })
                failed_count += 1
                continue

            try:
                from backend.app.services.ig_obsidian.frontmatter_validator import FrontmatterValidator
                from backend.app.services.ig_obsidian.review_system import ReviewSystem

                review_system = ReviewSystem(str(self.vault_path))
                frontmatter, content = review_system._read_markdown_file(full_path)

                validator = FrontmatterValidator()
                is_valid, readiness_score, missing_fields, warnings = validator.validate_frontmatter(
                    frontmatter=frontmatter,
                    content_body=content,
                    strict_mode=strict_mode
                )

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
            post_paths: List of post file paths (relative to vault)
            output_folder: Output folder for export packs (optional)

        Returns:
            Batch generation results
        """
        results = []
        total_posts = len(post_paths)
        success_count = 0
        failed_count = 0

        for post_path in post_paths:
            full_path = self.vault_path / post_path

            if not full_path.exists():
                results.append({
                    "post_path": post_path,
                    "status": "error",
                    "error": "File not found"
                })
                failed_count += 1
                continue

            try:
                from backend.app.services.ig_obsidian.export_pack_generator import ExportPackGenerator

                generator = ExportPackGenerator(str(self.vault_path))
                export_pack = generator.generate_export_pack(
                    post_path=post_path,
                    output_folder=output_folder
                )

                results.append({
                    "post_path": post_path,
                    "status": "success",
                    "export_pack": export_pack
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
            post_paths: List of post file paths (relative to vault)
            new_status: New status to set

        Returns:
            Batch update results
        """
        results = []
        total_posts = len(post_paths)
        success_count = 0
        failed_count = 0

        for post_path in post_paths:
            full_path = self.vault_path / post_path

            if not full_path.exists():
                results.append({
                    "post_path": post_path,
                    "status": "error",
                    "error": "File not found"
                })
                failed_count += 1
                continue

            try:
                from backend.app.services.ig_obsidian.review_system import ReviewSystem

                review_system = ReviewSystem(str(self.vault_path))
                frontmatter, content = review_system._read_markdown_file(full_path)

                frontmatter["status"] = new_status
                frontmatter["updated_at"] = datetime.now().isoformat()

                review_system._write_markdown_file(full_path, frontmatter, content)

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
            post_paths: List of post file paths (relative to vault)
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

