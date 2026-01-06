"""
Knob Effect Compiler

Compiles control knob values into three layers:
1. Prompt patches (injected to system message)
2. Model parameters (temperature, top_p, etc.)
3. Runtime policy (retrieval scope, confirmation thresholds, etc.)

Based on CONTROL_KNOB_DESIGN_SPEC.md v2.4
"""

import logging
from typing import Dict, List, Optional, Tuple
from backend.app.models.control_knob import (
    ControlKnob,
    ControlProfile,
    MasterValueRange,
    PromptPatch,
)
from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile

logger = logging.getLogger(__name__)


class MasterSlaveKnobSync:
    """
    主從旋鈕值同步器

    v2.1 規則：
    - 鎖定狀態下，從屬 knob 的 value 不可被直接寫入（只讀）
    - 解鎖後再鎖回去時，值會重新同步
    """

    def sync_slave_values(
        self,
        knob_values: Dict[str, int],
        knobs: List[ControlKnob]
    ) -> Dict[str, int]:
        """同步從屬旋鈕的值"""
        synced_values = knob_values.copy()

        for knob in knobs:
            if knob.master_knob_id and knob.is_locked_to_master:
                master_value = knob_values.get(knob.master_knob_id, 50)
                slave_value = self._compute_slave_value(master_value, knob.master_value_mapping)

                # 鎖定狀態下，強制覆蓋從屬值
                synced_values[knob.id] = slave_value

        return synced_values

    def _compute_slave_value(
        self,
        master_value: int,
        mapping: Optional[List[MasterValueRange]]
    ) -> int:
        """根據主旋鈕值計算從屬旋鈕值"""
        if not mapping:
            return 50  # 無映射時返回中值

        for range_item in mapping:
            if range_item.min_value <= master_value <= range_item.max_value:
                return range_item.slave_value

        # 邊界情況：找不到匹配區間，返回最後一個區間的值
        return mapping[-1].slave_value

    def validate_write(
        self,
        knob_id: str,
        new_value: int,
        knobs: List[ControlKnob]
    ) -> bool:
        """
        驗證是否允許寫入旋鈕值

        Returns:
            True: 允許寫入
            False: 拒絕寫入（從屬旋鈕鎖定狀態）
        """
        knob = next((k for k in knobs if k.id == knob_id), None)
        if not knob:
            return False

        # 從屬旋鈕且鎖定 → 不允許直接寫入
        if knob.master_knob_id and knob.is_locked_to_master:
            return False

        return True


class KnobEffectCompiler:
    """旋鈕效果編譯器"""

    def __init__(self, knobs: List[ControlKnob]):
        """
        初始化編譯器

        Args:
            knobs: 所有可用的旋鈕定義列表
        """
        self.knobs = knobs
        self.knob_map = {k.id: k for k in knobs}
        self.sync = MasterSlaveKnobSync()

    def _get_knob_by_id(self, knob_id: str) -> Optional[ControlKnob]:
        """根據 ID 獲取旋鈕定義"""
        return self.knob_map.get(knob_id)

    def compile(
        self,
        control_profile: ControlProfile,
        base_runtime_profile: Optional[WorkspaceRuntimeProfile] = None
    ) -> Tuple[str, Dict[str, float], WorkspaceRuntimeProfile, Dict[str, List[str]]]:
        """
        編譯旋鈕效果到三層輸出

        Returns:
            - prompt_addition: 要注入的 prompt 片段（system_append，向後兼容）
            - model_params: 調整後的模型參數
            - runtime_profile: 調整後的 Runtime Profile
            - patches_by_position: 按位置分組的 prompt patches
        """
        # 同步主從旋鈕值
        synced_values = self.sync.sync_slave_values(
            control_profile.knob_values,
            control_profile.knobs
        )

        # 1. 編譯 Prompt Patches（按 position 分組）
        patches_by_position = self._compile_prompt_patches(
            control_profile.knobs,
            synced_values
        )
        # 返回所有位置的 patches（供 prompt_builder 使用）
        # 目前只合併 system_append 作為主要輸出（向後兼容）
        prompt_addition = "\n".join(patches_by_position["system_append"])

        # 將其他位置的 patches 存儲在編譯結果中
        self._patches_by_position = patches_by_position

        # 2. 編譯 Model Params
        model_params = self._compile_model_params(
            control_profile.knobs,
            synced_values
        )

        # 3. 編譯 Runtime Profile
        runtime_profile = self._compile_runtime_profile(
            base_runtime_profile or WorkspaceRuntimeProfile(),
            control_profile.knobs,
            synced_values
        )

        return prompt_addition, model_params, runtime_profile, patches_by_position

    def _compile_prompt_patches(
        self,
        knobs: List[ControlKnob],
        knob_values: Dict[str, int]
    ) -> Dict[str, List[str]]:
        """
        編譯所有 prompt patch，按 position 分組

        Returns:
            Dict with keys: "system_prepend", "system_append", "context_section"
        """
        patches_by_position = {
            "system_prepend": [],
            "system_append": [],
            "context_section": []
        }

        for knob in knobs:
            if not knob.is_enabled or not knob.prompt_patch:
                continue

            value = knob_values.get(knob.id, knob.default_value)
            anchor_label = self._get_anchor_label(knob.anchors, value)

            # 檢查條件
            if knob.prompt_patch.condition:
                if not self._evaluate_condition(knob.prompt_patch.condition, value):
                    continue

            template = knob.prompt_patch.template

            # 動態計算模板變數
            template_vars = {
                "value": value,
                "anchor_label": anchor_label
            }

            # 特殊變數：根據 knob 類型計算
            if knob.id == "intervention_level":
                # 計算 max_questions：0-30 → 5, 31-70 → 2, 71-100 → 0
                if value <= 30:
                    template_vars["max_questions"] = 5
                elif value <= 70:
                    template_vars["max_questions"] = 2
                else:
                    template_vars["max_questions"] = 0

            # 使用 safe format（只替換存在的變數）
            try:
                compiled = template.format(**template_vars)
            except KeyError as e:
                logger.warning(f"Template variable missing for knob {knob.id}: {e}, using safe format")
                # 安全格式化：只替換已知變數
                compiled = template
                for key, val in template_vars.items():
                    compiled = compiled.replace(f"{{{key}}}", str(val))

            # 根據 position 分組
            position = knob.prompt_patch.position.value if hasattr(knob.prompt_patch.position, 'value') else str(knob.prompt_patch.position)
            if position == "system_prepend":
                patches_by_position["system_prepend"].append(compiled)
            elif position == "context_section":
                patches_by_position["context_section"].append(compiled)
            else:  # system_append (default)
                patches_by_position["system_append"].append(compiled)

        return patches_by_position

    def _get_anchor_label(self, anchors: List, value: int) -> str:
        """根據值找到最接近的 anchor label"""
        if not anchors:
            return str(value)

        closest = anchors[0]
        for anchor in anchors:
            if abs(anchor.value - value) < abs(closest.value - value):
                closest = anchor

        return closest.label

    def _evaluate_condition(self, condition: str, value: int) -> bool:
        """評估條件表達式（簡單實現）"""
        try:
            # 簡單的條件評估，例如 "value > 50"
            return eval(condition.replace("value", str(value)))
        except:
            logger.warning(f"Failed to evaluate condition: {condition}")
            return True

    def _compile_model_params(
        self,
        knobs: List[ControlKnob],
        knob_values: Dict[str, int]
    ) -> Dict[str, float]:
        """
        編譯模型參數

        ⚠️ v2.1 互斥規則：
        - temperature: 只有 convergence 可以動
        - presence_penalty: 只有 boldness 可以動
        - max_tokens: 只有 verbosity 可以動

        但支持所有 ModelParamsDelta 字段（top_p, frequency_penalty 等）
        """
        base_params = {
            "temperature": 0.7,
            "top_p": 0.9,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "max_tokens": 1000
        }

        # v2.1: 互斥映射表（param → 唯一主控旋鈕）
        EXCLUSIVE_PARAM_MAP = {
            "temperature": "convergence",
            "presence_penalty": "boldness",
            "max_tokens": "verbosity",
        }

        # ==================== v2.1: 互斥檢查 ====================
        param_writers = {}  # 記錄每個 param 被哪些旋鈕寫入
        for knob in knobs:
            if not knob.is_enabled:
                continue
            if knob.exclusive_param:
                if knob.exclusive_param in param_writers:
                    # ⚠️ 衝突！同一個 param 被多個旋鈕寫入
                    raise ValueError(
                        f"Parameter conflict: '{knob.exclusive_param}' is exclusively "
                        f"controlled by '{EXCLUSIVE_PARAM_MAP.get(knob.exclusive_param, 'unknown')}', "
                        f"but '{knob.id}' is also trying to modify it."
                    )
                param_writers[knob.exclusive_param] = knob.id

        # ==================== 處理所有旋鈕的 ModelParamsDelta ====================
        for knob in knobs:
            if not knob.is_enabled or not knob.model_params_delta:
                continue

            value = knob_values.get(knob.id, knob.default_value)
            delta = knob.model_params_delta

            # 計算 delta 值（如果 delta 是 None，則根據 value 計算）
            if knob.id == "convergence":
                # temperature: 發散(0) → temp +0.3, 收斂(100) → temp -0.3
                if delta.temperature_delta is not None:
                    base_params["temperature"] += delta.temperature_delta
                else:
                    base_params["temperature"] = 0.7 + (50 - value) / 166.67

            elif knob.id == "boldness":
                # presence_penalty: 保守(0) → penalty -0.3, 大膽(100) → penalty +0.5
                if delta.presence_penalty_delta is not None:
                    base_params["presence_penalty"] += delta.presence_penalty_delta
                else:
                    base_params["presence_penalty"] = (value - 50) / 125

            elif knob.id == "verbosity":
                # max_tokens: 一句話(0-30) → 100, 條列(31-70) → 500, 完整稿(71-100) → 2000
                if delta.max_tokens_delta is not None:
                    base_params["max_tokens"] += delta.max_tokens_delta
                else:
                    if value <= 30:
                        base_params["max_tokens"] = 100
                    elif value <= 70:
                        base_params["max_tokens"] = 500
                    else:
                        base_params["max_tokens"] = 2000

            # 支持其他 ModelParamsDelta 字段
            if delta.top_p_delta is not None:
                base_params["top_p"] = max(0.0, min(1.0, base_params["top_p"] + delta.top_p_delta))
            if delta.frequency_penalty_delta is not None:
                base_params["frequency_penalty"] += delta.frequency_penalty_delta

        # 確保參數在合理範圍內
        base_params["temperature"] = max(0.1, min(1.5, base_params["temperature"]))
        base_params["presence_penalty"] = max(-2.0, min(2.0, base_params["presence_penalty"]))
        base_params["frequency_penalty"] = max(-2.0, min(2.0, base_params["frequency_penalty"]))
        base_params["top_p"] = max(0.0, min(1.0, base_params["top_p"]))

        return base_params

    def _compile_runtime_profile(
        self,
        base_profile: WorkspaceRuntimeProfile,
        knobs: List[ControlKnob],
        knob_values: Dict[str, int]
    ) -> WorkspaceRuntimeProfile:
        """編譯 Runtime Profile"""
        # 創建副本
        profile = base_profile.model_copy(deep=True)

        for knob in knobs:
            if not knob.is_enabled or not knob.runtime_policy_delta:
                continue

            value = knob_values.get(knob.id, knob.default_value)
            delta = knob.runtime_policy_delta

            # 根據 knob 類型更新 profile
            if knob.id == "intervention_level":
                # 低介入 → 多問問題；高介入 → 假設默認值
                if value <= 30:
                    if profile.interaction_budget:
                        profile.interaction_budget.max_questions_per_turn = 5
                        profile.interaction_budget.assume_defaults = False
                elif value <= 70:
                    if profile.interaction_budget:
                        profile.interaction_budget.max_questions_per_turn = 2
                        profile.interaction_budget.assume_defaults = False
                else:
                    if profile.interaction_budget:
                        profile.interaction_budget.max_questions_per_turn = 0
                        profile.interaction_budget.assume_defaults = True

            elif knob.id == "tool_action_threshold":
                # 根據 value 直接設置，不依賴 delta（因為 delta 都是 None）
                if profile.confirmation_policy:
                    # 0-30: 只建議 → auto_read=False, confirm_soft_write=True
                    # 31-70: 提草稿 → auto_read=True, confirm_soft_write=True
                    # 71-100: 自動執行 → auto_read=True, confirm_soft_write=False
                    if value <= 30:
                        profile.confirmation_policy.auto_read = False
                        profile.confirmation_policy.confirm_soft_write = True
                    elif value <= 70:
                        profile.confirmation_policy.auto_read = True
                        profile.confirmation_policy.confirm_soft_write = True
                    else:
                        profile.confirmation_policy.auto_read = True
                        profile.confirmation_policy.confirm_soft_write = False

            elif knob.id == "confirmation_threshold":
                # 根據 value 直接設置
                if profile.confirmation_policy:
                    # 0-30: 寬鬆 → 只確認 external_write
                    # 31-70: 外部確認 → 確認 external_write 和 soft_write
                    # 71-100: 每步確認 → 所有操作都確認
                    if value <= 30:
                        profile.confirmation_policy.confirm_external_write = True
                        profile.confirmation_policy.confirm_soft_write = False
                    elif value <= 70:
                        profile.confirmation_policy.confirm_external_write = True
                        profile.confirmation_policy.confirm_soft_write = True
                    else:
                        profile.confirmation_policy.confirm_external_write = True
                        profile.confirmation_policy.confirm_soft_write = True
                        profile.confirmation_policy.auto_read = False  # 每步確認，連 read 也要確認

            elif knob.id == "retrieval_radius":
                # 檢索範圍：寫入 profile 的 metadata，供 context_builder 讀取
                if value <= 30:
                    retrieval_scope = "current_conversation"
                elif value <= 70:
                    retrieval_scope = "workspace"
                else:
                    retrieval_scope = "cross_workspace"

                # 寫入 metadata，確保 metadata 字典存在
                if profile.metadata is None:
                    profile.metadata = {}
                profile.metadata["retrieval_scope"] = retrieval_scope
                profile.metadata["retrieval_radius_value"] = value

                logger.info(f"Retrieval radius set to: {retrieval_scope} (value={value}), stored in profile.metadata")

        return profile

