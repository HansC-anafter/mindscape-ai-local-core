"""
Data Policy（資料留存/脫敏策略）

定義「raw trace vs safe summary」的明確邊界。

設計原則：
1. Langfuse 保存 raw（可設 retention / masking）
2. EGB Store 只保存 hashes、ids、統計指標、tool name 序列、來源 ids
3. 任何可能含 PII 的欄位先做 redaction

這樣「不用看 log」才是真的能對外說。
"""

import logging
import re
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from enum import Enum

logger = logging.getLogger(__name__)


class DataClassification(str, Enum):
    """資料分類"""

    PUBLIC = "public"  # 可公開
    INTERNAL = "internal"  # 內部使用
    SENSITIVE = "sensitive"  # 敏感資料
    PII = "pii"  # 個人識別資訊


class RetentionPolicy(str, Enum):
    """資料保留策略"""

    PERMANENT = "permanent"  # 永久保留
    LONG_TERM = "long_term"  # 長期（90天）
    SHORT_TERM = "short_term"  # 短期（7天）
    EPHEMERAL = "ephemeral"  # 臨時（24小時）
    NO_STORE = "no_store"  # 不存儲


@dataclass
class RedactionRule:
    """脫敏規則"""

    name: str
    pattern: str
    replacement: str = "[REDACTED]"
    classification: DataClassification = DataClassification.PII


@dataclass
class DataPolicyConfig:
    """資料策略配置"""

    # 保留策略
    raw_trace_retention: RetentionPolicy = RetentionPolicy.LONG_TERM
    evidence_retention: RetentionPolicy = RetentionPolicy.PERMANENT
    llm_explanation_retention: RetentionPolicy = RetentionPolicy.LONG_TERM

    # 存儲策略
    store_raw_output: bool = False  # 是否存儲原始輸出
    store_raw_input: bool = False  # 是否存儲原始輸入
    store_llm_explanations: bool = True  # 是否存儲 LLM 解釋

    # 脫敏配置
    redact_emails: bool = True
    redact_phones: bool = True
    redact_tokens: bool = True
    redact_urls: bool = False  # URL 通常不敏感
    redact_ips: bool = True
    redact_credit_cards: bool = True

    # 自定義脫敏規則
    custom_rules: List[RedactionRule] = field(default_factory=list)


class PIIRedactor:
    """
    PII 脫敏器

    用於在存儲前脫敏可能包含 PII 的文字。
    """

    # 預設脫敏規則
    DEFAULT_RULES = [
        RedactionRule(
            name="email",
            pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            replacement="[EMAIL]",
            classification=DataClassification.PII,
        ),
        RedactionRule(
            name="phone",
            pattern=r"\b(?:\+?1[-.\s]?)?(?:\([0-9]{3}\)|[0-9]{3})[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
            replacement="[PHONE]",
            classification=DataClassification.PII,
        ),
        RedactionRule(
            name="taiwan_phone",
            pattern=r"\b09[0-9]{8}\b",
            replacement="[PHONE]",
            classification=DataClassification.PII,
        ),
        RedactionRule(
            name="ip_address",
            pattern=r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b",
            replacement="[IP]",
            classification=DataClassification.SENSITIVE,
        ),
        RedactionRule(
            name="credit_card",
            pattern=r"\b(?:[0-9]{4}[-\s]?){3}[0-9]{4}\b",
            replacement="[CARD]",
            classification=DataClassification.PII,
        ),
        RedactionRule(
            name="api_key",
            pattern=r"\b(sk-|pk-|api[-_]?key[-_]?)[A-Za-z0-9]{20,}\b",
            replacement="[API_KEY]",
            classification=DataClassification.SENSITIVE,
        ),
        RedactionRule(
            name="jwt_token",
            pattern=r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
            replacement="[JWT]",
            classification=DataClassification.SENSITIVE,
        ),
        RedactionRule(
            name="bearer_token",
            pattern=r"\bBearer\s+[A-Za-z0-9_-]+\b",
            replacement="Bearer [TOKEN]",
            classification=DataClassification.SENSITIVE,
        ),
    ]

    def __init__(self, config: Optional[DataPolicyConfig] = None):
        """
        初始化 PII 脫敏器

        Args:
            config: 資料策略配置
        """
        self.config = config or DataPolicyConfig()
        self._rules = self._build_rules()
        self._compiled_patterns: Dict[str, re.Pattern] = {}
        self._compile_patterns()

    def _build_rules(self) -> List[RedactionRule]:
        """根據配置構建脫敏規則"""
        rules = []

        for rule in self.DEFAULT_RULES:
            if rule.name == "email" and self.config.redact_emails:
                rules.append(rule)
            elif rule.name in ["phone", "taiwan_phone"] and self.config.redact_phones:
                rules.append(rule)
            elif rule.name == "ip_address" and self.config.redact_ips:
                rules.append(rule)
            elif rule.name == "credit_card" and self.config.redact_credit_cards:
                rules.append(rule)
            elif (
                rule.name in ["api_key", "jwt_token", "bearer_token"]
                and self.config.redact_tokens
            ):
                rules.append(rule)

        # 添加自定義規則
        rules.extend(self.config.custom_rules)

        return rules

    def _compile_patterns(self) -> None:
        """編譯正則表達式"""
        for rule in self._rules:
            try:
                self._compiled_patterns[rule.name] = re.compile(
                    rule.pattern, re.IGNORECASE
                )
            except re.error as e:
                logger.warning(
                    f"DataPolicy: Invalid regex pattern for {rule.name}: {e}"
                )

    def redact(self, text: str) -> str:
        """
        脫敏文字

        Args:
            text: 原始文字

        Returns:
            脫敏後的文字
        """
        if not text:
            return text

        result = text
        for rule in self._rules:
            pattern = self._compiled_patterns.get(rule.name)
            if pattern:
                result = pattern.sub(rule.replacement, result)

        return result

    def redact_dict(
        self,
        data: Dict[str, Any],
        safe_keys: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        脫敏字典中的值

        Args:
            data: 原始字典
            safe_keys: 不需要脫敏的鍵

        Returns:
            脫敏後的字典
        """
        safe_keys = safe_keys or set()
        result = {}

        for key, value in data.items():
            if key in safe_keys:
                result[key] = value
            elif isinstance(value, str):
                result[key] = self.redact(value)
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value, safe_keys)
            elif isinstance(value, list):
                result[key] = [
                    self.redact(v) if isinstance(v, str) else v for v in value
                ]
            else:
                result[key] = value

        return result


class DataPolicy:
    """
    資料策略服務

    負責：
    1. 判斷資料的分類和保留策略
    2. 對資料進行脫敏
    3. 生成 safe summary（EGB Store 存儲的內容）

    ⚠️ P0-9 擴展：支援外部工具 payload 的分層留存/脫敏規則

    使用方式：
        policy = DataPolicy()

        # 脫敏
        safe_text = policy.redact(raw_text)

        # 生成 safe summary
        summary = policy.create_safe_summary(evidence)

        # 處理外部工具 payload
        safe_payload = policy.process_external_job_payload(payload, tool_name)
    """

    # EGB Store 允許存儲的欄位（白名單）
    SAFE_FIELDS = {
        # IDs
        "evidence_id",
        "run_id",
        "trace_id",
        "span_id",
        "intent_id",
        "decision_id",
        "playbook_id",
        "workspace_id",
        # ⚠️ P0-9 新增：外部 job IDs
        "external_job_id",
        "external_run_id",
        "tool_name",
        # Hashes
        "content_hash",
        "output_hash",
        "tool_args_hash",
        # ⚠️ P0-9 新增：外部 job 指紋
        "output_fingerprint",
        "key_fields_hash_map",
        # 統計指標
        "total_tokens",
        "total_cost_usd",
        "total_latency_ms",
        "llm_calls",
        "tool_calls",
        "retrieval_calls",
        "error_count",
        "retry_count",
        # 序列（只存名稱，不存內容）
        "tool_names",
        "source_names",
        "policy_names",
        # 狀態
        "status",
        "success",
        "passed",
        "strictness_level",
        "drift_level",
        "stability_score",
        # 時間戳
        "created_at",
        "updated_at",
        "started_at",
        "ended_at",
        # ⚠️ P0-9 新增：外部 job 相關
        "deep_link_to_external_log",
        "callback_received_at",
    }

    # ⚠️ P0-9：外部工具 payload 策略
    EXTERNAL_JOB_PAYLOAD_RETENTION_DAYS = 30  # Langfuse raw 保留天數
    EXTERNAL_JOB_PAYLOAD_PII_REDACTION = True  # 是否做 PII redaction
    EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB = 1  # 超過此大小只存 deep-link

    # 永不落盤的欄位（即使進 Langfuse 也要 redact）
    EXTERNAL_JOB_SENSITIVE_FIELDS = [
        "password",
        "token",
        "api_key",
        "secret",
        "email",
        "phone",
        "ssn",
        "credit_card",
        "authorization",
        "bearer",
        "x-api-key",
    ]

    # 只存 deep-link 的情況
    EXTERNAL_JOB_DEEP_LINK_ONLY_CONDITIONS = [
        "payload_size > 1MB",  # 太大只存 link
        "contains_sensitive_data",  # 含敏感資料只存 link
        "external_system_has_audit_log",  # 外部系統有審計日誌時只存 link
    ]

    def __init__(self, config: Optional[DataPolicyConfig] = None):
        """
        初始化 DataPolicy

        Args:
            config: 資料策略配置
        """
        self.config = config or DataPolicyConfig()
        self.redactor = PIIRedactor(config)

    def redact(self, text: str) -> str:
        """脫敏文字"""
        return self.redactor.redact(text)

    def redact_dict(
        self,
        data: Dict[str, Any],
        safe_keys: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """脫敏字典"""
        return self.redactor.redact_dict(data, safe_keys)

    def create_safe_summary(
        self,
        raw_data: Dict[str, Any],
        include_llm_explanation: bool = False,
    ) -> Dict[str, Any]:
        """
        創建 safe summary（EGB Store 存儲的內容）

        只保留 SAFE_FIELDS 中的欄位，其他內容丟棄或轉為 hash。

        Args:
            raw_data: 原始資料
            include_llm_explanation: 是否包含 LLM 解釋

        Returns:
            Safe summary
        """
        summary = {}

        for key, value in raw_data.items():
            if key in self.SAFE_FIELDS:
                summary[key] = value
            elif key == "llm_explanation" and include_llm_explanation:
                # LLM 解釋需要脫敏
                if self.config.store_llm_explanations and value:
                    summary[key] = self.redact(value)
            # 其他欄位不保留

        return summary

    def should_store_in_egb(self, field_name: str) -> bool:
        """判斷欄位是否應該存儲在 EGB Store"""
        return field_name in self.SAFE_FIELDS

    def get_retention_days(self, policy: RetentionPolicy) -> Optional[int]:
        """獲取保留天數"""
        if policy == RetentionPolicy.PERMANENT:
            return None
        elif policy == RetentionPolicy.LONG_TERM:
            return 90
        elif policy == RetentionPolicy.SHORT_TERM:
            return 7
        elif policy == RetentionPolicy.EPHEMERAL:
            return 1
        elif policy == RetentionPolicy.NO_STORE:
            return 0
        return None

    def get_expiry_date(self, policy: RetentionPolicy) -> Optional[datetime]:
        """獲取過期日期"""
        days = self.get_retention_days(policy)
        if days is None:
            return None
        if days == 0:
            return _utc_now()  # expire immediately
        return _utc_now() + timedelta(days=days)

    def process_external_job_payload(
        self,
        payload: Dict[str, Any],
        tool_name: str,
        deep_link: Optional[str] = None,
        contains_sensitive_data: bool = False,
    ) -> Dict[str, Any]:
        """
        處理外部工具 payload（P0-9 新增）

        ⚠️ P0-9 硬規則：分層策略
        - metadata 永久存儲
        - fingerprint 永久存儲
        - raw payload 可選（需 PII redaction，預設 30 天）
        - deep-link 永久存儲

        Args:
            payload: 外部工具 payload
            tool_name: 工具名稱
            deep_link: Deep link URL（可選）
            contains_sensitive_data: 是否包含敏感資料

        Returns:
            處理後的 payload（safe summary）
        """
        import sys
        import hashlib
        import json

        # 計算 payload 大小
        payload_size_mb = sys.getsizeof(json.dumps(payload)) / (1024 * 1024)

        # 判斷是否只存 deep-link
        should_store_deep_link_only = (
            payload_size_mb > self.EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB
            or contains_sensitive_data
            or deep_link is not None
        )

        result = {
            "tool_name": tool_name,
            "payload_size_mb": payload_size_mb,
        }

        if deep_link:
            result["deep_link_to_external_log"] = deep_link

        if should_store_deep_link_only:
            # 只存 deep-link，不存原始 payload
            result["store_strategy"] = "deep_link_only"
            return result

        # 計算 output_fingerprint
        payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        fingerprint = hashlib.sha256(payload_str.encode()).hexdigest()[:32]
        result["output_fingerprint"] = fingerprint
        result["output_fingerprint_type"] = "sha256"

        # 如果需要存儲 raw payload（可選）
        if self.config.store_raw_output:
            # 必須做 PII redaction
            if self.EXTERNAL_JOB_PAYLOAD_PII_REDACTION:
                redacted_payload = self.redact_dict(
                    payload,
                    safe_keys={
                        "tool_name",
                        "status",
                        "timestamp",
                    },  # 這些欄位不需要 redact
                )
                result["redacted_payload"] = redacted_payload
            else:
                result["raw_payload"] = payload

        result["store_strategy"] = "fingerprint_with_optional_raw"

        return result

    def should_store_external_payload_raw(
        self, payload_size_mb: float, contains_sensitive_data: bool, has_deep_link: bool
    ) -> bool:
        """
        判斷是否應該存儲外部 payload 的原始內容

        ⚠️ P0-9 硬規則：
        - payload > 1MB → 不存
        - 包含敏感資料 → 不存
        - 有 deep-link → 不存（只存 link）

        Args:
            payload_size_mb: Payload 大小（MB）
            contains_sensitive_data: 是否包含敏感資料
            has_deep_link: 是否有 deep-link

        Returns:
            bool: 是否應該存儲原始內容
        """
        if has_deep_link:
            return False  # 有 deep-link 就不存原始內容

        if payload_size_mb > self.EXTERNAL_JOB_PAYLOAD_MAX_SIZE_MB:
            return False  # 太大不存

        if contains_sensitive_data:
            return False  # 含敏感資料不存

        return True  # 其他情況可以存（但需要 PII redaction）


# 全局實例
_global_policy: Optional[DataPolicy] = None


def get_data_policy() -> DataPolicy:
    """獲取全局 DataPolicy 實例"""
    global _global_policy
    if _global_policy is None:
        _global_policy = DataPolicy()
    return _global_policy
