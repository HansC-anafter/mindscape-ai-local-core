"""
Content Checker for IG Post

Checks content for medical/investment claims, copyright issues, personal data,
and brand tone compliance.
"""
import logging
import re
from typing import Dict, Any, List, Optional

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

    def check_content(self, content: str, frontmatter: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Check content for compliance issues

        Args:
            content: Post content text
            frontmatter: Post frontmatter (optional)

        Returns:
            {
                "risk_flags": List[str],
                "warnings": List[str],
                "checks": Dict[str, Any]
            }
        """
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


