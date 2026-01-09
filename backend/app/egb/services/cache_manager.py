"""
EGB Cache Manager

EGB 快取管理器，確保 cache key 包含治理上下文，避免「調了旋鈕但畫面還是舊的」。

⚠️ P0-4 硬規則：所有 cache key 必須包含「治理上下文」hash
"""

import logging
from typing import Optional, Callable, Any, Dict
from functools import wraps

from backend.app.egb.schemas.correlation_ids import CorrelationIds

logger = logging.getLogger(__name__)


class EGBCacheManager:
    """
    EGB 快取管理器

    Cache key 包含治理上下文，確保：
    - policy_version 改了 → cache miss
    - strictness_level 改了 → cache miss
    - mind_lens_level 改了 → cache miss

    ⚠️ P0-4 硬規則：所有 cache key 必須包含「治理上下文」hash
    """

    def __init__(self, cache_backend=None):
        """
        初始化 Cache Manager

        Args:
            cache_backend: 快取後端（Redis、內存等），預設使用內存
        """
        self._cache: Dict[str, Any] = cache_backend or {}
        self._is_dict_cache = not hasattr(self._cache, 'get')

    def cache_key_for_drift(
        self,
        correlation_ids: CorrelationIds,
        baseline_run_id: str
    ) -> str:
        """
        漂移報告的快取鍵

        ⚠️ P0 硬規則：必須包含治理上下文 hash

        格式：drift:{intent_id}:{run_id}:{baseline_run_id}:{context_hash}

        context_hash 包含（使用 CorrelationIds.get_cache_context_hash()）：
        - policy_version
        - strictness_level
        - mind_lens_level
        - playbook_id（若需要更細粒度，可擴展）

        理由：
        - 避免「UI 切 Lens/Strictness，看起來像是怎麼切都不變」
        - 確保治理維度變化時 cache 正確失效
        """
        ctx_hash = correlation_ids.get_cache_context_hash()
        return f"drift:{correlation_ids.intent_id}:{correlation_ids.run_id}:{baseline_run_id}:{ctx_hash}"

    def cache_key_for_evidence(
        self,
        run_id: str,
        strictness_level: int,
        policy_version: Optional[str] = None
    ) -> str:
        """
        結構化證據的快取鍵

        ⚠️ P0-D 修正：必須包含 policy_version
        因為 semantic drift 的 key_fields_hash 依賴 policy config whitelist
        """
        if policy_version:
            return f"evidence:{run_id}:s{strictness_level}:p{policy_version}"
        return f"evidence:{run_id}:s{strictness_level}"

    def cache_key_for_profile(
        self,
        intent_id: str,
        policy_version: str
    ) -> str:
        """
        意圖證據剖面的快取鍵

        注意：policy_version 改變會影響穩定度計算
        """
        return f"profile:{intent_id}:{policy_version}"

    async def get(self, cache_key: str) -> Optional[Any]:
        """從快取獲取"""
        if self._is_dict_cache:
            return self._cache.get(cache_key)
        else:
            return await self._cache.get(cache_key)

    async def set(self, cache_key: str, value: Any, ttl: Optional[int] = None) -> None:
        """設置快取"""
        if self._is_dict_cache:
            self._cache[cache_key] = value
        else:
            await self._cache.set(cache_key, value, ttl=ttl)

    async def delete(self, cache_key: str) -> None:
        """刪除快取"""
        if self._is_dict_cache:
            self._cache.pop(cache_key, None)
        else:
            await self._cache.delete(cache_key)

    async def get_or_compute(
        self,
        cache_key: str,
        compute_fn: Callable[[], Any],
        ttl_seconds: int = 3600
    ) -> Any:
        """
        優先從快取取，沒有才計算

        Args:
            cache_key: 快取鍵
            compute_fn: 計算函數（async）
            ttl_seconds: TTL（秒）

        Returns:
            快取值或計算結果
        """
        cached = await self.get(cache_key)
        if cached is not None:
            return cached

        result = await compute_fn()
        await self.set(cache_key, result, ttl=ttl_seconds)
        return result

    def invalidate_drift_cache(self, intent_id: str) -> None:
        """
        失效該 intent 的所有 drift cache

        使用方式：當用戶調整 strictness/lens 時調用
        """
        # TODO: 如果使用 Redis，可以用 pattern 刪除
        # 目前內存 cache 需要遍歷（效率較低，但 MVP 可用）
        keys_to_delete = [
            key for key in (self._cache.keys() if self._is_dict_cache else [])
            if key.startswith(f"drift:{intent_id}:")
        ]
        for key in keys_to_delete:
            if self._is_dict_cache:
                self._cache.pop(key, None)

