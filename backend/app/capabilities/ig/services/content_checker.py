"""
Content Checker for IG Post

Checks content for medical/investment claims, copyright issues, personal data,
and brand tone compliance.
"""
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml

from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


class ContentChecker:
    """
    Checks IG Post content for compliance issues

    Supports:
    - Medical/investment claims checking
    - Copyright infringement warnings
    - Personal data/sensitive information checking
    - Brand tone checking
    """

    # Medical claim keywords (Chinese)
    MEDICAL_KEYWORDS = [
        "治療", "治癒", "療效", "藥效", "藥品", "藥物", "處方", "診斷",
        "疾病", "病症", "症狀", "病患", "患者", "醫療", "醫院", "醫生",
        "醫師", "護理", "手術", "開刀", "癌症", "腫瘤", "糖尿病", "高血壓"
    ]

    # Investment claim keywords (Chinese)
    INVESTMENT_KEYWORDS = [
        "投資", "理財", "股票", "基金", "期貨", "外匯", "保證獲利", "穩賺",
        "高報酬", "零風險", "內線", "內幕", "推薦股票", "推薦投資", "代操",
        "代客操作", "保證收益", "保本", "獲利保證"
    ]

    # Copyright risk keywords
    COPYRIGHT_KEYWORDS = [
        "轉載", "轉貼", "分享", "引用", "來源", "出處", "原作者", "版權",
        "著作權", "侵權", "抄襲", "盜用"
    ]

    # Personal data patterns
    PERSONAL_DATA_PATTERNS = [
        r'\d{4}[-/]\d{2}[-/]\d{2}',  # Date of birth
        r'\d{10,11}',  # Phone number (10-11 digits)
        r'[A-Z0-9]{6,}',  # ID number pattern
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # Email
    ]

    # Brand tone keywords (positive)
    BRAND_TONE_POSITIVE = [
        "專業", "用心", "品質", "服務", "價值", "信任", "可靠", "誠信"
    ]

    # Brand tone keywords (negative - should avoid)
    BRAND_TONE_NEGATIVE = [
        "便宜", "低價", "促銷", "特價", "限時", "倒數", "緊急", "最後機會"
    ]

    def __init__(self, workspace_storage: Optional[WorkspaceStorage] = None):
        """
        Initialize Content Checker

        Args:
            workspace_storage: WorkspaceStorage instance (optional, for reading from file)
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
        if not self.storage:
            raise ValueError("WorkspaceStorage is required for reading from file")

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

    def check_content(
        self,
        content: Optional[str] = None,
        frontmatter: Optional[Dict[str, Any]] = None,
        post_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check content for compliance issues

        Args:
            content: Post content text (optional if post_path provided)
            frontmatter: Post frontmatter (optional)
            post_path: Path to post file (optional, if provided will read from file)

        Returns:
            {
                "risk_flags": List[str],
                "warnings": List[str],
                "checks": Dict[str, Any],
                "is_safe": bool
            }
        """
        # Read from file if post_path provided
        if post_path and self.storage:
            try:
                content, frontmatter = self._read_content_from_file(post_path)
            except Exception as e:
                logger.error(f"Failed to read content from file: {e}")
                return {
                    "risk_flags": ["error"],
                    "warnings": [f"Failed to read content: {str(e)}"],
                    "checks": {},
                    "is_safe": False
                }

        if not content:
            return {
                "risk_flags": ["error"],
                "warnings": ["No content provided"],
                "checks": {},
                "is_safe": False
            }

        risk_flags = []
        warnings = []
        checks = {}

        # Check medical claims
        medical_check = self._check_medical_claims(content)
        if medical_check["found"]:
            risk_flags.append("醫療")
            warnings.extend(medical_check["warnings"])
        checks["medical"] = medical_check

        # Check investment claims
        investment_check = self._check_investment_claims(content)
        if investment_check["found"]:
            risk_flags.append("投資")
            warnings.extend(investment_check["warnings"])
        checks["investment"] = investment_check

        # Check copyright issues
        copyright_check = self._check_copyright(content)
        if copyright_check["found"]:
            risk_flags.append("侵權")
            warnings.extend(copyright_check["warnings"])
        checks["copyright"] = copyright_check

        # Check personal data
        personal_data_check = self._check_personal_data(content)
        if personal_data_check["found"]:
            risk_flags.append("個資")
            warnings.extend(personal_data_check["warnings"])
        checks["personal_data"] = personal_data_check

        # Check brand tone
        brand_tone_check = self._check_brand_tone(content)
        if brand_tone_check["issues"]:
            warnings.extend(brand_tone_check["warnings"])
        checks["brand_tone"] = brand_tone_check

        return {
            "risk_flags": risk_flags,
            "warnings": warnings,
            "checks": checks,
            "is_safe": len(risk_flags) == 0
        }

    def _check_medical_claims(self, content: str) -> Dict[str, Any]:
        """Check for medical claims"""
        found_keywords = []

        for keyword in self.MEDICAL_KEYWORDS:
            if keyword in content:
                found_keywords.append(keyword)

        return {
            "found": len(found_keywords) > 0,
            "keywords_found": found_keywords,
            "warnings": [
                f"發現醫療相關用語: {', '.join(found_keywords)}。請確認是否符合法規要求。"
            ] if found_keywords else []
        }

    def _check_investment_claims(self, content: str) -> Dict[str, Any]:
        """Check for investment claims"""
        found_keywords = []

        for keyword in self.INVESTMENT_KEYWORDS:
            if keyword in content:
                found_keywords.append(keyword)

        return {
            "found": len(found_keywords) > 0,
            "keywords_found": found_keywords,
            "warnings": [
                f"發現投資相關用語: {', '.join(found_keywords)}。請確認是否符合法規要求。"
            ] if found_keywords else []
        }

    def _check_copyright(self, content: str) -> Dict[str, Any]:
        """Check for copyright issues"""
        found_keywords = []

        for keyword in self.COPYRIGHT_KEYWORDS:
            if keyword in content:
                found_keywords.append(keyword)

        return {
            "found": len(found_keywords) > 0,
            "keywords_found": found_keywords,
            "warnings": [
                f"發現版權相關用語: {', '.join(found_keywords)}。請確認是否已取得授權。"
            ] if found_keywords else []
        }

    def _check_personal_data(self, content: str) -> Dict[str, Any]:
        """Check for personal data patterns"""
        found_patterns = []

        for pattern in self.PERSONAL_DATA_PATTERNS:
            matches = re.findall(pattern, content)
            if matches:
                found_patterns.extend(matches)

        return {
            "found": len(found_patterns) > 0,
            "patterns_found": found_patterns,
            "warnings": [
                f"發現可能的個人資料: {len(found_patterns)} 處。請確認是否已取得同意。"
            ] if found_patterns else []
        }

    def _check_brand_tone(self, content: str) -> Dict[str, Any]:
        """Check brand tone compliance"""
        positive_found = []
        negative_found = []

        for keyword in self.BRAND_TONE_POSITIVE:
            if keyword in content:
                positive_found.append(keyword)

        for keyword in self.BRAND_TONE_NEGATIVE:
            if keyword in content:
                negative_found.append(keyword)

        warnings = []
        if negative_found:
            warnings.append(
                f"發現可能不符合品牌調性的用語: {', '.join(negative_found)}。建議使用更專業的表述。"
            )

        return {
            "positive_keywords": positive_found,
            "negative_keywords": negative_found,
            "issues": len(negative_found) > 0,
            "warnings": warnings
        }

