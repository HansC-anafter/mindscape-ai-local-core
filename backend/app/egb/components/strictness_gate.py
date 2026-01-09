"""
Strictness Gate（嚴謹度閘門）

根據 strictness level 檢查輸出是否符合要求。

⚠️ P0-6 硬規則：輸出契約必須明確
- Level 1：結構化輸出檢查
- Level 2：證據引用檢查（evidence_refs 格式驗證）
"""

import logging
from typing import Any, Optional, List, Dict
from dataclasses import dataclass, field

from backend.app.egb.schemas.structured_evidence import StructuredEvidence

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """Gate 檢查結果"""
    passed: bool
    level: int
    reason: Optional[str] = None
    missing_refs: List[str] = field(default_factory=list)


class StrictnessGate:
    """
    嚴謹度閘門

    根據 strictness level 檢查輸出是否符合要求。

    ⚠️ P0-6 硬規則：輸出契約必須明確
    - Level 1：結構化輸出檢查
    - Level 2：證據引用檢查（evidence_refs 格式驗證）
    """

    def __init__(self):
        """初始化 StrictnessGate"""
        pass

    async def check_level_1(self, output: Any) -> GateResult:
        """
        Level 1: 結構化輸出檢查

        ⚠️ v1.2.3 修正：Level 1 只檢查結構化輸出，不強制 evidence_refs
        """
        # 檢查是否為有效 JSON
        if not isinstance(output, dict):
            return GateResult(
                passed=False,
                level=1,
                reason="Output is not a valid JSON object"
            )

        # 檢查是否符合基本結構（可選，根據實際 schema）
        # TODO: 可以加入 JSON schema 驗證

        return GateResult(passed=True, level=1)

    async def check_level_2(
        self,
        output: Any,
        evidence: StructuredEvidence
    ) -> GateResult:
        """
        Level 2: 證據引用檢查

        ⚠️ P0 硬規則：輸出契約（必須明確）

        **1. 資料型別與位置**：
        - 欄位名：`evidence_refs`（必填）
        - 型別：`string[]`（List[str]）
        - 位置：structured output 的根層級

        **2. 格式規範**（Canonical 格式，全文件統一）：
        ```json
        {
          "evidence_refs": ["span:<langfuse_span_id>", "chunk:<retrieval_chunk_id>", "policy:<policy_node_id>"]
        }
        ```
        例如：`["span:abc123", "chunk:def456", "policy:ghi789"]`

        **3. 最小數量要求**：
        - 至少 1 個引用（`len(evidence_refs) >= 1`）
        - 必須引用到「關鍵結論所依據的 evidence」（避免要求引用全部，太重）

        **4. 機械檢查規則**（strictness ≥ 2 時執行）：
        1. 必須有 `evidence_refs` 欄位且為 `string[]`
        2. `len(evidence_refs) >= 1`
        3. **所有引用的 ID 必須在 `evidence.get_evidence_ids()` 回傳的白名單中**（完全機械檢查）
        4. 至少引用一個 retrieval 或 tool 的證據（不能只有 LLM）

        若不符合，GateResult.passed = False，reason = "Missing or invalid evidence_refs"

        ⚠️ v1.2.3 修正：只有 strictness ≥ 2 才強制檢查
        - strictness = 1：只檢查結構化輸出（Level 1）
        - strictness ≥ 2：檢查結構化輸出 + evidence_refs（Level 2）
        """
        # 先檢查 Level 1
        level1_result = await self.check_level_1(output)
        if not level1_result.passed:
            return GateResult(
                passed=False,
                level=2,
                reason=f"Level 1 check failed: {level1_result.reason}"
            )

        # 檢查 evidence_refs 欄位
        if not isinstance(output, dict):
            return GateResult(
                passed=False,
                level=2,
                reason="Output is not a valid JSON object"
            )

        evidence_refs = output.get("evidence_refs")
        if not evidence_refs:
            return GateResult(
                passed=False,
                level=2,
                reason="Missing evidence_refs field"
            )

        if not isinstance(evidence_refs, list):
            return GateResult(
                passed=False,
                level=2,
                reason="evidence_refs must be a list (string[])"
            )

        if len(evidence_refs) < 1:
            return GateResult(
                passed=False,
                level=2,
                reason="evidence_refs must contain at least 1 reference"
            )

        # 獲取白名單
        allowed_ids = evidence.get_evidence_ids()

        # 檢查所有引用的 ID 是否在白名單中
        invalid_refs = []
        has_retrieval_or_tool = False

        for ref in evidence_refs:
            if not isinstance(ref, str):
                invalid_refs.append(str(ref))
                continue

            # ⚠️ P0-2：檢查格式（必須是 span:/chunk:/policy: 前綴）
            if not (ref.startswith("span:") or ref.startswith("chunk:") or ref.startswith("policy:")):
                invalid_refs.append(ref)
                continue

            # 檢查是否在白名單中
            if ref not in allowed_ids:
                invalid_refs.append(ref)
                continue

            # 檢查是否引用 retrieval 或 tool
            if ref.startswith("chunk:") or ref.startswith("span:"):
                has_retrieval_or_tool = True

        if invalid_refs:
            return GateResult(
                passed=False,
                level=2,
                reason=f"Invalid evidence_refs: {invalid_refs}",
                missing_refs=invalid_refs
            )

        if not has_retrieval_or_tool:
            return GateResult(
                passed=False,
                level=2,
                reason="Must reference at least one retrieval or tool evidence (not just LLM)"
            )

        return GateResult(passed=True, level=2)

    async def check_level_3(self, draft: Any, verified: Any) -> GateResult:
        """
        Level 3: 兩階段驗證

        檢查 draft 與 verified 的一致性。
        """
        # TODO: 實現 Level 3 檢查
        return GateResult(passed=True, level=3)

    async def check(
        self,
        output: Any,
        evidence: StructuredEvidence,
        strictness_level: int
    ) -> GateResult:
        """
        根據 strictness_level 執行對應的檢查

        Args:
            output: 輸出（structured output）
            evidence: 結構化證據
            strictness_level: 嚴謹度等級

        Returns:
            GateResult: 檢查結果
        """
        if strictness_level >= 2:
            return await self.check_level_2(output, evidence)
        elif strictness_level >= 1:
            return await self.check_level_1(output)
        else:
            # Level 0：不檢查
            return GateResult(passed=True, level=0)

