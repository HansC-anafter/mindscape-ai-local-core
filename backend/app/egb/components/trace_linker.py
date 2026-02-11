"""
TraceLinker（證據關聯器）

職責：把 intent_id / decision_id / playbook_id / run_id 綁到 trace_id / span_id
這是 EGB 的第一個元件，負責建立治理層與觀測層的關聯。
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import uuid

from backend.app.egb.schemas.correlation_ids import CorrelationIds

logger = logging.getLogger(__name__)


@dataclass
class TraceLink:
    """Trace 關聯記錄"""
    link_id: str
    correlation_ids: CorrelationIds
    trace_id: str
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "link_id": self.link_id,
            "correlation_ids": self.correlation_ids.to_dict(),
            "trace_id": self.trace_id,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class LinkResult:
    """關聯結果"""
    success: bool
    link: Optional[TraceLink] = None
    error: Optional[str] = None


class TraceLinker:
    """
    證據關聯器

    ⚠️ P0-3 硬規則：TraceLinker = 查索引 / 建關聯（DB）
    Propagation = 只能在一個地方做（EGBTracePropagation.trace_context()）

    負責：
    1. 建立 run 與 trace 的關聯（索引查詢）
    2. 查詢某意圖下的所有 runs
    3. 查詢 run_id 對應的 CorrelationIds

    使用場景：
    - 當 Playbook 開始執行時，註冊 run（建立索引）
    - 當需要查看意圖的歷史執行時，查詢關聯
    - 在前端 IntentCard 上顯示執行歷史時

    ⚠️ 禁止：TraceLinker 做 propagation（那是 EGBTracePropagation 的職責）
    """

    def __init__(self, store=None):
        """
        初始化 TraceLinker

        Args:
            store: 可選的持久化存儲（預設使用內存）
        """
        self._links: Dict[str, TraceLink] = {}  # run_id -> TraceLink
        self._intent_index: Dict[str, List[str]] = {}  # intent_id -> [run_ids]
        self.store = store

    async def register_run(
        self,
        correlation_ids: CorrelationIds
    ) -> LinkResult:
        """
        註冊 run（建立索引）

        ⚠️ P0-1 硬規則：run_id == trace_id（單一真相）
        correlation_ids.run_id 直接就是 Langfuse trace.id

        Args:
            correlation_ids: 關聯 ID 體系（必須包含 run_id）

        Returns:
            LinkResult: 註冊結果
        """
        try:
            # ⚠️ P0-1：run_id 就是 trace_id，不需要設置
            run_id = correlation_ids.run_id
            if not run_id:
                return LinkResult(success=False, error="Missing run_id in correlation_ids")

            # 創建關聯記錄
            link = TraceLink(
                link_id=str(uuid.uuid4()),
                correlation_ids=correlation_ids,
                trace_id=run_id,  # ⚠️ P0-1：trace_id = run_id
                created_at=_utc_now(),
            )

            # ⚠️ 優先保存到 store（如果可用）
            # ⚠️ save_run_index 已支持「存在則更新」，不會重複寫入
            if self.store:
                from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore
                if isinstance(self.store, EvidenceProfileStore):
                    try:
                        await self.store.save_run_index(
                            correlation_ids=correlation_ids,
                            status="pending",
                        )
                        logger.debug(f"TraceLinker: Saved/updated run {run_id} to store")
                    except Exception as e:
                        logger.warning(f"TraceLinker: Failed to save run index: {e}")
                        # 不拋出異常，允許繼續執行（可能已存在）

            # 存儲關聯（內存索引，作為 cache）
            self._links[run_id] = link

            # 更新 intent 索引
            intent_id = correlation_ids.intent_id
            if intent_id not in self._intent_index:
                self._intent_index[intent_id] = []
            if run_id not in self._intent_index[intent_id]:
                self._intent_index[intent_id].append(run_id)

            logger.info(
                f"TraceLinker: Registered run {run_id} for intent {intent_id}"
            )

            return LinkResult(success=True, link=link)

        except Exception as e:
            logger.error(f"TraceLinker: Failed to register run: {e}")
            return LinkResult(success=False, error=str(e))

    async def get_runs_by_intent(
        self,
        intent_id: str,
        limit: int = 100
    ) -> List[CorrelationIds]:
        """
        查詢某意圖下的所有 runs

        ⚠️ 優先從 store 查詢，fallback 到記憶體索引

        Args:
            intent_id: 意圖 ID
            limit: 返回數量限制

        Returns:
            List[CorrelationIds]: 關聯 ID 列表（按時間倒序）
        """
        # ⚠️ 優先從 store 查詢（如果有）
        if self.store:
            from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore
            if isinstance(self.store, EvidenceProfileStore):
                run_indices = await self.store.get_runs_by_intent(
                    intent_id=intent_id,
                    limit=limit,
                    only_success=False,  # 獲取所有 runs
                )
                # 轉換為 CorrelationIds
                correlation_ids_list = []
                for run_index in run_indices:
                    correlation_ids = CorrelationIds.from_dict(run_index.correlation_ids_json)
                    correlation_ids_list.append(correlation_ids)
                return correlation_ids_list

        # Fallback：從記憶體索引查詢
        run_ids = self._intent_index.get(intent_id, [])
        links = [
            self._links[run_id]
            for run_id in run_ids
            if run_id in self._links
        ]

        # 按時間倒序排列
        links.sort(key=lambda x: x.created_at, reverse=True)

        return [link.correlation_ids for link in links[:limit]]

    async def get_run_by_id(self, run_id: str) -> Optional[CorrelationIds]:
        """
        根據 run_id 獲取 CorrelationIds

        ⚠️ P0-1：run_id 是單一真相
        ⚠️ 優先從 store 查詢，fallback 到內存索引
        """
        # ⚠️ 優先從 store 查詢（如果可用）
        if self.store:
            from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore
            if isinstance(self.store, EvidenceProfileStore):
                run_index = await self.store.get_run_index(run_id)
                if run_index:
                    # 從 correlation_ids_json 重建 CorrelationIds
                    correlation_ids = CorrelationIds.from_dict(run_index.correlation_ids_json)
                    return correlation_ids

        # Fallback：從內存索引查詢
        link = self._links.get(run_id)
        return link.correlation_ids if link else None

    async def get_recent_successful_runs(
        self,
        intent_id: str,
        policy_version: Optional[str] = None,  # ⚠️ P0-5：可選的 policy_version 過濾
        limit: int = 10,
        only_success: bool = True,  # ⚠️ P0-10 新增：只選 outcome == "success" 的
    ) -> List[CorrelationIds]:
        """
        獲取最近成功的 runs（供 BaselinePicker 使用）

        ⚠️ P0-5 硬規則：預設只在同 policy_version 內選
        ⚠️ P0-10：支援 only_success 參數（只選 outcome == "success" 的）

        ⚠️ 優先使用 store 持久化查詢，fallback 到記憶體索引
        """
        # ⚠️ P0-10：優先從 store 查詢（如果有）
        if self.store:
            from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore
            if isinstance(self.store, EvidenceProfileStore):
                run_indices = await self.store.get_runs_by_intent(
                    intent_id=intent_id,
                    policy_version=policy_version,
                    limit=limit,
                    only_success=only_success,
                )
                # 轉換為 CorrelationIds
                correlation_ids_list = []
                for run_index in run_indices:
                    correlation_ids = CorrelationIds.from_dict(run_index.correlation_ids_json)
                    correlation_ids_list.append(correlation_ids)
                return correlation_ids_list

        # Fallback：從記憶體索引查詢
        all_runs = await self.get_runs_by_intent(intent_id, limit=limit * 2)

        # 過濾同 policy_version（如果指定）
        if policy_version:
            filtered = [r for r in all_runs if r.policy_version == policy_version]
        else:
            filtered = all_runs

        # ⚠️ P0-10：記憶體索引沒有 outcome 資訊，只能返回所有 runs
        # 實際的過濾應該在 store 層面進行（通過 is_success 欄位）
        return filtered[:limit]

    async def get_link_by_run_id(self, run_id: str) -> Optional[TraceLink]:
        """
        根據 run_id 獲取關聯記錄（向後相容）

        ⚠️ P0-1：run_id == trace_id，所以這個方法等於 get_run_by_id
        """
        return self._links.get(run_id)

    async def get_latest_run_for_intent(
        self,
        intent_id: str
    ) -> Optional[TraceLink]:
        """獲取某意圖的最新執行"""
        links = await self.get_traces_by_intent(intent_id, limit=1)
        return links[0] if links else None

    async def get_baseline_run_for_intent(
        self,
        intent_id: str,
        current_run_id: str
    ) -> Optional[TraceLink]:
        """
        獲取用於比較的基準 run

        預設使用當前 run 的前一次成功執行
        """
        links = await self.get_traces_by_intent(intent_id, limit=10)

        for link in links:
            if link.correlation_ids.run_id != current_run_id:
                return link

        return None

    # ❌ 已移除：propagate_ids_to_span()
    # ⚠️ P0-3 硬規則：TraceLinker 不負責 propagation
    # Propagation 只能在 EGBTracePropagation.trace_context() 中做

    def get_statistics(self) -> Dict[str, Any]:
        """獲取統計資訊"""
        return {
            "total_links": len(self._links),
            "total_intents": len(self._intent_index),
            "links_by_intent": {
                intent_id: len(run_ids)
                for intent_id, run_ids in self._intent_index.items()
            },
        }

