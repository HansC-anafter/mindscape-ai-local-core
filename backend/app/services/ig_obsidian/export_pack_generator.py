"""
Export Pack Generator for IG Post

Generates complete export pack including post.md, hashtags.txt, CTA variants,
and checklist.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

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

    def __init__(self, vault_path: str):
        """
        Initialize Export Pack Generator

        Args:
            vault_path: Path to Obsidian Vault
        """
        self.vault_path = Path(vault_path).expanduser().resolve()

    def generate_export_pack(
        self,
        post_folder: str,
        post_content: str,
        frontmatter: Dict[str, Any],
        hashtags: List[str],
        cta_variants: Optional[List[str]] = None,
        assets_list: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Generate complete export pack

        Args:
            post_folder: Post folder path (relative to vault)
            post_content: Post content text
            frontmatter: Post frontmatter
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
        post_path = self.vault_path / post_folder
        export_folder = post_path / "export"
        export_folder.mkdir(parents=True, exist_ok=True)

        files_generated = []
        export_pack = {}

        # Generate post.md
        post_md_path = export_folder / "post.md"
        post_md_content = self._generate_post_md(post_content, frontmatter)
        post_md_path.write_text(post_md_content, encoding="utf-8")
        files_generated.append(str(post_md_path.relative_to(self.vault_path)))
        export_pack["post_md"] = post_md_content

        # Generate hashtags.txt
        hashtags_txt_path = export_folder / "hashtags.txt"
        hashtags_txt_content = self._generate_hashtags_txt(hashtags)
        hashtags_txt_path.write_text(hashtags_txt_content, encoding="utf-8")
        files_generated.append(str(hashtags_txt_path.relative_to(self.vault_path)))
        export_pack["hashtags_txt"] = hashtags_txt_content

        # Generate CTA variants
        if cta_variants:
            cta_variants_path = export_folder / "cta_variants.txt"
            cta_variants_content = self._generate_cta_variants_txt(cta_variants)
            cta_variants_path.write_text(cta_variants_content, encoding="utf-8")
            files_generated.append(str(cta_variants_path.relative_to(self.vault_path)))
            export_pack["cta_variants_txt"] = cta_variants_content

        # Generate checklist
        checklist_path = export_folder / "checklist.md"
        checklist_content = self._generate_checklist(frontmatter, assets_list)
        checklist_path.write_text(checklist_content, encoding="utf-8")
        files_generated.append(str(checklist_path.relative_to(self.vault_path)))
        export_pack["checklist_md"] = checklist_content

        return {
            "export_pack_path": str(export_folder.relative_to(self.vault_path)),
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


