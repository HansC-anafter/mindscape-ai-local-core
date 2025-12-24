"""
Export Pack Generator for IG Post

Generates complete export pack including post.md, hashtags.txt, CTA variants,
and checklist.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import yaml
import re

from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class ExportPackGenerator:
    """
    Generates complete export pack for IG Post

    Supports:
    - Post markdown file generation
    - Hashtags text file generation
    - CTA variants generation
    - Checklist generation
    """

    def __init__(self, workspace_storage: WorkspaceStorage):
        """
        Initialize Export Pack Generator

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

    def _read_content_from_file(self, post_path: str) -> tuple[str, Dict[str, Any]]:
        """
        Read content and frontmatter from Markdown file

        Args:
            post_path: Path to post file (relative to workspace or Obsidian-style)

        Returns:
            Tuple of (content, frontmatter)
        """
        full_path = self._resolve_post_path(post_path)

        if not full_path.exists():
            raise FileNotFoundError(f"Post file not found: {full_path}")

        with open(full_path, "r", encoding="utf-8") as f:
            file_content = f.read()

        # Parse frontmatter
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, file_content, re.DOTALL)

        if match:
            frontmatter_str = match.group(1)
            content = match.group(2)
            try:
                frontmatter = yaml.safe_load(frontmatter_str) or {}
                return content, frontmatter
            except yaml.YAMLError as e:
                logger.error(f"Failed to parse frontmatter YAML: {e}")
                return file_content, {}
        else:
            return file_content, {}

    def generate_export_pack(
        self,
        post_path: Optional[str] = None,
        post_content: Optional[str] = None,
        frontmatter: Optional[Dict[str, Any]] = None,
        hashtags: List[str] = None,
        cta_variants: Optional[List[str]] = None,
        assets_list: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Generate complete export pack

        Args:
            post_path: Post file path (relative to workspace or Obsidian-style, optional if post_content provided)
            post_content: Post content text (optional if post_path provided)
            frontmatter: Post frontmatter (optional if post_path provided)
            hashtags: List of hashtags
            cta_variants: List of CTA variants (optional)
            assets_list: List of assets (optional)

        Returns:
            {
                "export_pack_path": str,
                "files_generated": List[str],
                "export_pack": Dict[str, Any]
            }
        """
        # Read from file if post_path provided
        if post_path and not post_content:
            try:
                post_content, frontmatter = self._read_content_from_file(post_path)
            except Exception as e:
                logger.error(f"Failed to read content from file: {e}")
                raise

        if not post_content or not frontmatter:
            raise ValueError("Either post_path or (post_content + frontmatter) must be provided")

        # Determine post slug from frontmatter or post_path
        if post_path:
            # Extract post slug from path
            if "_" in post_path:
                post_slug = post_path.split("_")[-1].replace(".md", "").replace("/", "")
            else:
                post_slug = post_path.replace(".md", "").replace("/", "")
        else:
            # Try to get from frontmatter
            post_slug = frontmatter.get("slug") or "post"

        # Get post directory
        post_dir = self.storage.get_post_path(post_slug)
        export_folder = post_dir / "export"
        export_folder.mkdir(parents=True, exist_ok=True)

        files_generated = []
        export_pack = {}

        # Generate post.md
        post_md_path = export_folder / "post.md"
        post_md_content = self._generate_post_md(post_content, frontmatter)
        post_md_path.write_text(post_md_content, encoding="utf-8")
        files_generated.append(str(post_md_path.relative_to(self.storage.get_capability_root())))
        export_pack["post_md"] = post_md_content

        # Generate hashtags.txt
        if hashtags:
            hashtags_txt_path = export_folder / "hashtags.txt"
            hashtags_txt_content = self._generate_hashtags_txt(hashtags)
            hashtags_txt_path.write_text(hashtags_txt_content, encoding="utf-8")
            files_generated.append(str(hashtags_txt_path.relative_to(self.storage.get_capability_root())))
            export_pack["hashtags_txt"] = hashtags_txt_content

        # Generate CTA variants
        if cta_variants:
            cta_variants_path = export_folder / "cta_variants.txt"
            cta_variants_content = self._generate_cta_variants_txt(cta_variants)
            cta_variants_path.write_text(cta_variants_content, encoding="utf-8")
            files_generated.append(str(cta_variants_path.relative_to(self.storage.get_capability_root())))
            export_pack["cta_variants_txt"] = cta_variants_content

        # Generate checklist
        checklist_path = export_folder / "checklist.md"
        checklist_content = self._generate_checklist(frontmatter, assets_list)
        checklist_path.write_text(checklist_content, encoding="utf-8")
        files_generated.append(str(checklist_path.relative_to(self.storage.get_capability_root())))
        export_pack["checklist_md"] = checklist_content

        return {
            "export_pack_path": str(export_folder.relative_to(self.storage.get_capability_root())),
            "files_generated": files_generated,
            "export_pack": export_pack
        }

    def _generate_post_md(self, post_content: str, frontmatter: Dict[str, Any]) -> str:
        """Generate post.md content"""
        lines = ["---"]

        # Write frontmatter
        for key, value in frontmatter.items():
            if isinstance(value, list):
                lines.append(f"{key}: {value}")
            elif isinstance(value, dict):
                lines.append(f"{key}:")
                for sub_key, sub_value in value.items():
                    lines.append(f"  {sub_key}: {sub_value}")
            else:
                lines.append(f"{key}: {value}")

        lines.append("---")
        lines.append("")
        lines.append(post_content)

        return "\n".join(lines)

    def _generate_hashtags_txt(self, hashtags: List[str]) -> str:
        """Generate hashtags.txt content"""
        # Format: one hashtag per line, or space-separated
        return "\n".join(hashtags) + "\n"

    def _generate_cta_variants_txt(self, cta_variants: List[str]) -> str:
        """Generate CTA variants text file"""
        lines = ["# CTA Variants", ""]
        for i, cta in enumerate(cta_variants, 1):
            lines.append(f"## Variant {i}")
            lines.append(cta)
            lines.append("")

        return "\n".join(lines)

    def _generate_checklist(
        self,
        frontmatter: Dict[str, Any],
        assets_list: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Generate checklist.md content"""
        lines = [
            "# IG Post Checklist",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Content Checklist",
            ""
        ]

        # Content checks
        content_checks = [
            ("Frontmatter complete", self._check_frontmatter_complete(frontmatter)),
            ("Post content ready", frontmatter.get("status") in ["ready", "exported", "published"]),
            ("Hashtags prepared", frontmatter.get("hashtag_groups") is not None),
            ("CTA defined", frontmatter.get("cta_type") is not None),
        ]

        for check_name, check_result in content_checks:
            status = "✅" if check_result else "❌"
            lines.append(f"- {status} {check_name}")

        lines.append("")
        lines.append("## Asset Checklist")
        lines.append("")

        # Asset checks
        if assets_list:
            required_assets = frontmatter.get("required_assets", [])
            for asset in assets_list:
                asset_name = asset.get("name", "Unknown")
                naming_valid = asset.get("naming_valid", False)
                status = "✅" if naming_valid else "❌"
                lines.append(f"- {status} {asset_name} (naming: {'valid' if naming_valid else 'invalid'})")

            # Check for missing assets
            if required_assets:
                lines.append("")
                lines.append("### Required Assets")
                for req_asset in required_assets:
                    found = any(asset.get("name") == req_asset for asset in assets_list)
                    status = "✅" if found else "❌"
                    lines.append(f"- {status} {req_asset}")
        else:
            lines.append("- ⚠️ No assets scanned")

        lines.append("")
        lines.append("## Pre-Publish Checklist")
        lines.append("")

        pre_publish_checks = [
            "Content reviewed",
            "Hashtags checked (no blocked hashtags)",
            "Assets validated (size, format)",
            "CTA tested",
            "Risk flags reviewed",
            "Brand tone checked"
        ]

        for check in pre_publish_checks:
            lines.append(f"- [ ] {check}")

        return "\n".join(lines)

    def _check_frontmatter_complete(self, frontmatter: Dict[str, Any]) -> bool:
        """Check if frontmatter is complete"""
        required_fields = ["workspace_id", "domain", "intent", "status", "share_policy"]
        return all(field in frontmatter for field in required_fields)

