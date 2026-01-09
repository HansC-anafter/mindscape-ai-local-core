"""
Baseline Picker（基準選擇器）

用於選擇漂移計算的基準 run。
這是 EGB 的一等公民服務，確保 DriftScorer、UI、快取鍵的一致性。

支援三種基準策略：
1. LAST_SUCCESS：同一 intent 下最近一次成功 run
2. PINNED_BASELINE：使用者指定一個基準（用於 Experiment）
3. STABLE_BASELINE：最近 N 次中 drift 最低的一次（意圖的穩定參考）
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from backend.app.egb.schemas.correlation_ids import CorrelationIds
from backend.app.egb.schemas.structured_evidence import StructuredEvidence

logger = logging.getLogger(__name__)


class BaselineStrategy(str, Enum):
    """基準選擇策略"""
    LAST_SUCCESS = "last_success"        # 最近一次成功執行
    PINNED = "pinned"                     # 使用者指定的基準
    STABLE = "stable"                     # 最穩定的一次
    PREVIOUS = "previous"                 # 上一次執行（不管成功與否）


@dataclass
class BaselineCandidate:
    """基準候選"""
    run_id: str
    correlation_ids: CorrelationIds
    executed_at: datetime
    is_success: bool
    drift_score: Optional[float] = None  # 與其他 run 的平均 drift

    # 元數據
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BaselineSelection:
    """基準選擇結果"""
    strategy: BaselineStrategy
    selected: Optional[BaselineCandidate] = None
    candidates_count: int = 0
    reason: str = ""

    @property
    def has_baseline(self) -> bool:
        return self.selected is not None

    @property
    def baseline_run_id(self) -> Optional[str]:
        return self.selected.run_id if self.selected else None


@dataclass
class PinnedBaseline:
    """釘選的基準"""
    intent_id: str
    baseline_run_id: str
    pinned_by: str
    pinned_at: datetime
    reason: Optional[str] = None


class BaselinePicker:
    """
    基準選擇器

    負責：
    1. 根據策略選擇最佳基準
    2. 管理釘選的基準
    3. 提供快取鍵一致性

    使用方式：
        picker = BaselinePicker(trace_linker, evidence_cache)
        selection = await picker.pick_baseline(
            intent_id="xxx",
            current_run_id="yyy",
            strategy=BaselineStrategy.LAST_SUCCESS
        )
    """

    # 用於 STABLE 策略的參數
    STABLE_WINDOW_SIZE = 10  # 最近 N 次

    def __init__(
        self,
        trace_linker=None,
        evidence_cache: Dict[str, StructuredEvidence] = None,
        orchestrator=None,  # ⚠️ 新增：用於重建證據
    ):
        """
        初始化 BaselinePicker

        Args:
            trace_linker: TraceLinker 實例
            evidence_cache: 證據快取（run_id -> StructuredEvidence）
            orchestrator: EGBOrchestrator 實例（可選，用於重建證據）
        """
        self.trace_linker = trace_linker
        self.evidence_cache = evidence_cache or {}
        self.orchestrator = orchestrator  # ⚠️ 新增

        # 釘選基準存儲
        self._pinned_baselines: Dict[str, PinnedBaseline] = {}  # intent_id -> PinnedBaseline

    async def pick_baseline(
        self,
        intent_id: str,
        current_policy_version: str,  # ⚠️ P0-5 新增：當前 run 的 policy_version
        strategy: BaselineStrategy = BaselineStrategy.LAST_SUCCESS,
        allow_cross_version: bool = False,  # ⚠️ P0-5 新增：是否允許跨版本對比
        current_run_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> BaselineSelection:
        """
        選擇基準

        ⚠️ P0-5 硬規則：預設只在同 policy_version 內選 baseline
        理由：不同 policy_version 的 key_fields_hash_map 的 pointer 集合可能不同

        Args:
            intent_id: 意圖 ID
            current_policy_version: 當前 run 的 policy_version
            strategy: 選擇策略
            allow_cross_version: 是否允許跨版本對比（預設 False）
            current_run_id: 當前 run ID（會被排除）
            workspace_id: 工作空間 ID（可選）

        Returns:
            BaselineSelection: 選擇結果
        """
        # 獲取候選（⚠️ P0-5：預設只在同 policy_version 內選）
        candidates = await self._get_candidates(
            intent_id=intent_id,
            current_run_id=current_run_id,
            policy_version=current_policy_version if not allow_cross_version else None,
            workspace_id=workspace_id,
        )

        if not candidates:
            return BaselineSelection(
                strategy=strategy,
                selected=None,
                candidates_count=0,
                reason="No baseline candidates found for this intent",
            )

        # 根據策略選擇
        if strategy == BaselineStrategy.PINNED:
            return await self._pick_pinned(intent_id, candidates)
        elif strategy == BaselineStrategy.LAST_SUCCESS:
            return self._pick_last_success(candidates)
        elif strategy == BaselineStrategy.STABLE:
            return await self._pick_stable(candidates)
        elif strategy == BaselineStrategy.PREVIOUS:
            return self._pick_previous(candidates)
        else:
            # 預設使用 LAST_SUCCESS
            return self._pick_last_success(candidates)

    async def _get_candidates(
        self,
        intent_id: str,
        current_run_id: Optional[str] = None,
        policy_version: Optional[str] = None,  # ⚠️ P0-5 新增：可選的 policy_version 過濾
        workspace_id: Optional[str] = None,
    ) -> List[BaselineCandidate]:
        """
        獲取基準候選列表

        ⚠️ P0-5 硬規則：如果指定 policy_version，只返回同版本的候選
        """
        candidates = []

        if self.trace_linker:
            # ⚠️ P0-5：從 TraceLinker 獲取（支援 policy_version 過濾）
            # ⚠️ P0-10：只獲取 outcome == "success" 的 runs
            correlation_ids_list = await self.trace_linker.get_recent_successful_runs(
                intent_id=intent_id,
                policy_version=policy_version,
                limit=self.STABLE_WINDOW_SIZE * 2,  # 取多一點
                only_success=True,  # ⚠️ P0-10：只選成功的（is_success == True，即 outcome == "success"）
            )

            for correlation_ids in correlation_ids_list:
                if current_run_id and correlation_ids.run_id == current_run_id:
                    continue  # 排除當前 run

                # 構建候選（使用 correlation_ids）
                # ⚠️ P0-10：檢查是否有證據，並判斷 success（考慮 RunOutcome）
                evidence = self.evidence_cache.get(correlation_ids.run_id)
                is_success = True

                # ⚠️ P0-10：從 store 查詢實際 status 和 outcome（如果可用）
                if self.trace_linker and hasattr(self.trace_linker, 'store'):
                    from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore
                    if isinstance(self.trace_linker.store, EvidenceProfileStore):
                        run_index = await self.trace_linker.store.get_run_index(correlation_ids.run_id)
                        if run_index:
                            # 使用 store 的 is_success（已考慮 outcome）
                            is_success = run_index.is_success
                        else:
                            # 如果 store 沒有，fallback 到 evidence 檢查
                            if evidence:
                                is_success = evidence.metrics.error_count == 0
                            else:
                                is_success = False  # 沒有證據且 store 也沒有，視為失敗
                elif evidence:
                    # 基礎檢查：error_count = 0
                    is_success = evidence.metrics.error_count == 0
                else:
                    # ⚠️ 如果沒有 evidence 且沒有 store，嘗試從 orchestrator 重建
                    if hasattr(self, 'orchestrator') and self.orchestrator:
                        # 從 orchestrator 重建證據
                        baseline_evidence = await self.orchestrator._rebuild_evidence(
                            correlation_ids.run_id,
                            correlation_ids
                        )
                        if baseline_evidence:
                            # 存入 cache
                            self.evidence_cache[correlation_ids.run_id] = baseline_evidence
                            evidence = baseline_evidence
                            is_success = evidence.metrics.error_count == 0
                        else:
                            continue  # 無法重建，跳過
                    else:
                        continue  # 無法判斷，跳過

                candidate = BaselineCandidate(
                    run_id=correlation_ids.run_id,
                    correlation_ids=correlation_ids,
                    executed_at=correlation_ids.created_at,
                    is_success=is_success,
                )
                candidates.append(candidate)

        # 按時間倒序排列
        candidates.sort(key=lambda c: c.executed_at, reverse=True)

        return candidates

    def _pick_last_success(
        self,
        candidates: List[BaselineCandidate]
    ) -> BaselineSelection:
        """選擇最近一次成功的 run"""
        success_candidates = [c for c in candidates if c.is_success]

        if not success_candidates:
            # 沒有成功的，退化到上一次
            return self._pick_previous(candidates)

        selected = success_candidates[0]  # 已經按時間排序

        return BaselineSelection(
            strategy=BaselineStrategy.LAST_SUCCESS,
            selected=selected,
            candidates_count=len(candidates),
            reason=f"Selected most recent successful run from {len(success_candidates)} successful candidates",
        )

    def _pick_previous(
        self,
        candidates: List[BaselineCandidate]
    ) -> BaselineSelection:
        """選擇上一次 run"""
        if not candidates:
            return BaselineSelection(
                strategy=BaselineStrategy.PREVIOUS,
                selected=None,
                candidates_count=0,
                reason="No previous runs found",
            )

        selected = candidates[0]  # 已經按時間排序

        return BaselineSelection(
            strategy=BaselineStrategy.PREVIOUS,
            selected=selected,
            candidates_count=len(candidates),
            reason=f"Selected previous run (success={selected.is_success})",
        )

    async def _pick_pinned(
        self,
        intent_id: str,
        candidates: List[BaselineCandidate]
    ) -> BaselineSelection:
        """選擇釘選的基準"""
        pinned = self._pinned_baselines.get(intent_id)

        if not pinned:
            # 沒有釘選，退化到 LAST_SUCCESS
            logger.info(f"BaselinePicker: No pinned baseline for {intent_id}, falling back to LAST_SUCCESS")
            return self._pick_last_success(candidates)

        # 找到釘選的候選
        for candidate in candidates:
            if candidate.run_id == pinned.baseline_run_id:
                return BaselineSelection(
                    strategy=BaselineStrategy.PINNED,
                    selected=candidate,
                    candidates_count=len(candidates),
                    reason=f"Using pinned baseline (pinned by {pinned.pinned_by})",
                )

        # 釘選的 run 不在候選中（可能已過期）
        logger.warning(f"BaselinePicker: Pinned baseline {pinned.baseline_run_id} not found in candidates")
        return self._pick_last_success(candidates)

    async def _pick_stable(
        self,
        candidates: List[BaselineCandidate]
    ) -> BaselineSelection:
        """選擇最穩定的 run"""
        # 只考慮成功的 candidates
        success_candidates = [c for c in candidates if c.is_success]

        if not success_candidates:
            return self._pick_previous(candidates)

        # 限制窗口大小
        window = success_candidates[:self.STABLE_WINDOW_SIZE]

        # 計算每個 candidate 與其他 candidates 的平均 drift
        # （需要有 evidence 才能計算）
        candidates_with_drift = []

        for candidate in window:
            evidence = self.evidence_cache.get(candidate.run_id)
            if not evidence:
                continue

            # 計算與其他 candidates 的平均 drift
            total_drift = 0.0
            drift_count = 0

            for other in window:
                if other.run_id == candidate.run_id:
                    continue
                other_evidence = self.evidence_cache.get(other.run_id)
                if not other_evidence:
                    continue

                # 簡化版 drift 計算（基於 output_hash 和 tool_path）
                drift = 0.0
                if evidence.output_hash != other_evidence.output_hash:
                    drift += 0.5
                if evidence.tool_path.path_signature != other_evidence.tool_path.path_signature:
                    drift += 0.5

                total_drift += drift
                drift_count += 1

            if drift_count > 0:
                candidate.drift_score = total_drift / drift_count
                candidates_with_drift.append(candidate)

        if not candidates_with_drift:
            # 無法計算 drift，退化到 LAST_SUCCESS
            return self._pick_last_success(candidates)

        # 選擇 drift 最低的
        candidates_with_drift.sort(key=lambda c: c.drift_score or 1.0)
        selected = candidates_with_drift[0]

        return BaselineSelection(
            strategy=BaselineStrategy.STABLE,
            selected=selected,
            candidates_count=len(candidates),
            reason=f"Selected most stable run (drift_score={selected.drift_score:.2f})",
        )

    # ========== 釘選管理 ==========

    def pin_baseline(
        self,
        intent_id: str,
        baseline_run_id: str,
        pinned_by: str,
        reason: Optional[str] = None,
    ) -> PinnedBaseline:
        """
        釘選基準

        Args:
            intent_id: 意圖 ID
            baseline_run_id: 要釘選的 run ID
            pinned_by: 釘選者 ID
            reason: 釘選原因

        Returns:
            PinnedBaseline
        """
        pinned = PinnedBaseline(
            intent_id=intent_id,
            baseline_run_id=baseline_run_id,
            pinned_by=pinned_by,
            pinned_at=datetime.utcnow(),
            reason=reason,
        )

        self._pinned_baselines[intent_id] = pinned

        logger.info(
            f"BaselinePicker: Pinned baseline {baseline_run_id} for intent {intent_id}"
        )

        return pinned

    def unpin_baseline(self, intent_id: str) -> bool:
        """
        取消釘選

        Args:
            intent_id: 意圖 ID

        Returns:
            bool: 是否成功取消
        """
        if intent_id in self._pinned_baselines:
            del self._pinned_baselines[intent_id]
            logger.info(f"BaselinePicker: Unpinned baseline for intent {intent_id}")
            return True
        return False

    def get_pinned_baseline(self, intent_id: str) -> Optional[PinnedBaseline]:
        """獲取釘選的基準"""
        return self._pinned_baselines.get(intent_id)

    # ========== 快取鍵 ==========

    @staticmethod
    def get_cache_key(
        intent_id: str,
        current_run_id: str,
        baseline_run_id: str,
    ) -> str:
        """
        生成一致的快取鍵

        用於 DriftReport 的快取。

        Args:
            intent_id: 意圖 ID
            current_run_id: 當前 run ID
            baseline_run_id: 基準 run ID

        Returns:
            快取鍵字串
        """
        return f"drift:{intent_id}:{current_run_id}:{baseline_run_id}"

    @staticmethod
    def get_profile_cache_key(
        workspace_id: str,
        intent_id: str,
    ) -> str:
        """
        生成 IntentEvidenceProfile 的快取鍵

        Args:
            workspace_id: 工作空間 ID
            intent_id: 意圖 ID

        Returns:
            快取鍵字串
        """
        return f"profile:{workspace_id}:{intent_id}"

