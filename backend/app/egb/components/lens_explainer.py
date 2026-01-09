"""
LensExplainer（心智鏡解釋器）

職責：用 LLM 把結構化證據翻譯成人話
這是 EGB 的第五個元件，也是唯一需要 LLM 的元件。

關鍵設計：
- 只在需要時觸發（用戶點擊「解釋」時）
- 輸入是精煉後的證據摘要，不是原始 trace
- 有嚴格的 token 預算控制
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from backend.app.egb.schemas.drift_report import (
    RunDriftReport,
    DriftExplanation,
)
from backend.app.egb.schemas.evidence_profile import IntentEvidenceProfile
from backend.app.egb.schemas.governance_prescription import GovernancePrescription

logger = logging.getLogger(__name__)


@dataclass
class ExplanationResult:
    """解釋結果"""
    explanation: str
    tokens_used: int
    model_used: str
    confidence: float


class LensExplainer:
    """
    心智鏡解釋器

    負責：
    1. 將漂移報告翻譯成人話
    2. 總結證據剖面
    3. 解釋治理處方

    設計原則：
    - 只在用戶請求時觸發，不主動呼叫
    - 輸入是結構化數據，不是原始 log
    - 有嚴格的 token 預算控制
    """

    # Token 預算配置
    MAX_INPUT_TOKENS = 2000
    MAX_OUTPUT_TOKENS = 500
    DEFAULT_MODEL = "gpt-4o-mini"  # 使用較便宜的模型

    def __init__(self, llm_client=None):
        """
        初始化 LensExplainer

        Args:
            llm_client: LLM 客戶端（可選，用於測試注入）
        """
        self.llm_client = llm_client
        self._total_tokens_used = 0

    async def explain_drift(
        self,
        drift_report: RunDriftReport,
        attribution: List[DriftExplanation],
        user_context: Optional[str] = None
    ) -> ExplanationResult:
        """
        解釋為什麼漂移（人話）

        Args:
            drift_report: 漂移報告
            attribution: 漂移歸因列表
            user_context: 用戶提供的上下文

        Returns:
            ExplanationResult: 解釋結果
        """
        # 構建精簡的 prompt
        prompt = self._build_drift_explanation_prompt(
            drift_report, attribution, user_context
        )

        # 如果沒有 LLM 客戶端，返回基於規則的解釋
        if not self.llm_client:
            return self._generate_rule_based_drift_explanation(
                drift_report, attribution
            )

        # 呼叫 LLM
        try:
            response = await self._call_llm(prompt)
            return ExplanationResult(
                explanation=response["content"],
                tokens_used=response["tokens_used"],
                model_used=response["model"],
                confidence=0.9,
            )
        except Exception as e:
            logger.error(f"LensExplainer: LLM call failed: {e}")
            return self._generate_rule_based_drift_explanation(
                drift_report, attribution
            )

    async def summarize_evidence(
        self,
        evidence_profile: IntentEvidenceProfile
    ) -> ExplanationResult:
        """
        總結證據剖面

        Args:
            evidence_profile: 意圖證據剖面

        Returns:
            ExplanationResult: 總結結果
        """
        # 構建精簡的 prompt
        prompt = self._build_evidence_summary_prompt(evidence_profile)

        if not self.llm_client:
            return self._generate_rule_based_evidence_summary(evidence_profile)

        try:
            response = await self._call_llm(prompt)
            return ExplanationResult(
                explanation=response["content"],
                tokens_used=response["tokens_used"],
                model_used=response["model"],
                confidence=0.85,
            )
        except Exception as e:
            logger.error(f"LensExplainer: LLM call failed: {e}")
            return self._generate_rule_based_evidence_summary(evidence_profile)

    async def explain_prescription(
        self,
        prescription: GovernancePrescription
    ) -> ExplanationResult:
        """
        解釋治理處方

        Args:
            prescription: 治理處方

        Returns:
            ExplanationResult: 解釋結果
        """
        prompt = self._build_prescription_explanation_prompt(prescription)

        if not self.llm_client:
            return self._generate_rule_based_prescription_explanation(prescription)

        try:
            response = await self._call_llm(prompt)
            return ExplanationResult(
                explanation=response["content"],
                tokens_used=response["tokens_used"],
                model_used=response["model"],
                confidence=0.85,
            )
        except Exception as e:
            logger.error(f"LensExplainer: LLM call failed: {e}")
            return self._generate_rule_based_prescription_explanation(prescription)

    def _build_drift_explanation_prompt(
        self,
        drift_report: RunDriftReport,
        attribution: List[DriftExplanation],
        user_context: Optional[str] = None
    ) -> str:
        """構建漂移解釋的 prompt"""
        # 精簡數據，控制 token
        data = {
            "drift_level": drift_report.drift_level.value,
            "overall_score": f"{drift_report.overall_drift_score:.2f}",
            "top_drifts": [
                {
                    "type": e.drift_type.value,
                    "explanation": e.explanation[:100],  # 截斷
                    "severity": e.severity,
                }
                for e in attribution[:3]  # 最多 3 個
            ],
        }

        prompt = f"""你是一個 AI 治理解釋助手。請用簡潔的中文解釋以下漂移報告，讓非技術用戶理解。

漂移數據：
- 漂移等級: {data['drift_level']}
- 整體分數: {data['overall_score']}
- 主要漂移:
"""
        for drift in data['top_drifts']:
            prompt += f"  - {drift['type']}: {drift['explanation']} (嚴重程度: {drift['severity']})\n"

        if user_context:
            prompt += f"\n用戶背景: {user_context[:200]}\n"

        prompt += """
請提供：
1. 一句話總結（20字內）
2. 主要原因說明（50字內）
3. 是否需要關注（是/否，並簡短說明）

保持回答簡潔，總共不超過 150 字。"""

        return prompt

    def _build_evidence_summary_prompt(
        self,
        evidence_profile: IntentEvidenceProfile
    ) -> str:
        """構建證據總結的 prompt"""
        prompt = f"""請用簡潔的中文總結以下意圖執行情況：

執行統計：
- 總執行次數: {evidence_profile.total_runs}
- 成功率: {evidence_profile.success_rate:.1%}
- 平均成本: ${evidence_profile.avg_cost_per_run:.4f}
- 穩定度: {evidence_profile.stability_score:.1%}
- 漂移等級: {evidence_profile.drift_level.value}

請提供一段 50 字內的總結，說明這個意圖的整體執行狀況。"""

        return prompt

    def _build_prescription_explanation_prompt(
        self,
        prescription: GovernancePrescription
    ) -> str:
        """構建處方解釋的 prompt"""
        recommendations = [
            f"- {r.knob_name}: {r.current_value} → {r.suggested_value}"
            for r in prescription.recommendations[:3]
        ]

        prompt = f"""請用簡潔的中文解釋以下治理建議：

建議調整：
{chr(10).join(recommendations)}

信心度: {prescription.confidence:.0%}

請說明：
1. 為什麼建議這樣調整（30字內）
2. 調整後的預期效果（30字內）

總共不超過 80 字。"""

        return prompt

    async def _call_llm(self, prompt: str) -> Dict[str, Any]:
        """呼叫 LLM（需要注入 llm_client）"""
        # 這裡是佔位實現
        # 實際應該調用配置的 LLM 服務
        if self.llm_client:
            response = await self.llm_client.generate(
                prompt=prompt,
                max_tokens=self.MAX_OUTPUT_TOKENS,
                model=self.DEFAULT_MODEL,
            )
            return response

        raise ValueError("LLM client not configured")

    def _generate_rule_based_drift_explanation(
        self,
        drift_report: RunDriftReport,
        attribution: List[DriftExplanation]
    ) -> ExplanationResult:
        """生成基於規則的漂移解釋（不使用 LLM）"""
        parts = []

        # 總結
        level_map = {
            "stable": "穩定",
            "mild": "輕微變化",
            "moderate": "中度變化",
            "high": "顯著變化",
        }
        level_text = level_map.get(drift_report.drift_level.value, "變化")
        parts.append(f"本次執行{level_text}。")

        # 主要原因
        if attribution:
            top = attribution[0]
            parts.append(f"主要原因：{top.explanation[:50]}。")

        # 是否需要關注
        if drift_report.requires_attention:
            parts.append("建議關注此變化。")
        else:
            parts.append("無需特別關注。")

        return ExplanationResult(
            explanation="".join(parts),
            tokens_used=0,
            model_used="rule_based",
            confidence=0.7,
        )

    def _generate_rule_based_evidence_summary(
        self,
        evidence_profile: IntentEvidenceProfile
    ) -> ExplanationResult:
        """生成基於規則的證據總結（不使用 LLM）"""
        stability_text = "穩定" if evidence_profile.stability_score > 0.7 else (
            "較穩定" if evidence_profile.stability_score > 0.5 else "不穩定"
        )

        summary = (
            f"此意圖已執行 {evidence_profile.total_runs} 次，"
            f"成功率 {evidence_profile.success_rate:.0%}，"
            f"整體{stability_text}。"
        )

        return ExplanationResult(
            explanation=summary,
            tokens_used=0,
            model_used="rule_based",
            confidence=0.7,
        )

    def _generate_rule_based_prescription_explanation(
        self,
        prescription: GovernancePrescription
    ) -> ExplanationResult:
        """生成基於規則的處方解釋（不使用 LLM）"""
        if not prescription.recommendations:
            return ExplanationResult(
                explanation="目前無需調整。",
                tokens_used=0,
                model_used="rule_based",
                confidence=0.7,
            )

        primary = prescription.primary_recommendation
        explanation = f"建議將{primary.knob_name}從 {primary.current_value} 調整為 {primary.suggested_value}，以提高執行穩定性。"

        return ExplanationResult(
            explanation=explanation,
            tokens_used=0,
            model_used="rule_based",
            confidence=0.7,
        )

    def get_token_usage(self) -> int:
        """獲取累計 token 使用量"""
        return self._total_tokens_used

