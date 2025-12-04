# LLM Provider 禁止 Fallback 修復

**日期**：2025-12-04
**要求**：禁止任何 fallback 和無腦挑選第一個模型的行為，所有模型選用都必須用戶指定

---

## 🎯 核心原則

1. **禁止 fallback**：不允許自動選擇第一個可用的 provider
2. **必須用戶指定**：所有 LLM provider 選擇都必須基於用戶配置的 `chat_model`
3. **明確報錯**：如果用戶未配置或指定的 provider 不可用，直接報錯，不 fallback

---

## ✅ 已完成的修復

### 1. 修改 `LLMProviderManager.get_provider()`

**文件**：`backend/app/services/agent_runner.py`

**修改前**：
```python
def get_provider(self, provider_name: Optional[str] = None) -> Optional[LLMProvider]:
    """Get LLM provider by name, or return first available"""
    if not self.providers:
        return None

    if provider_name and provider_name in self.providers:
        return self.providers[provider_name]

    # Return first available provider  ❌ 禁止此行為
    return list(self.providers.values())[0]
```

**修改後**：
```python
def get_provider(self, provider_name: Optional[str] = None) -> Optional[LLMProvider]:
    """
    Get LLM provider by name

    Args:
        provider_name: Provider name (required, no fallback)

    Returns:
        LLMProvider instance or None if not found

    Raises:
        ValueError: If provider_name is not specified
    """
    if not provider_name:
        raise ValueError(
            "provider_name is required. Cannot use fallback to first available provider. "
            "Please specify the provider name explicitly."
        )

    if not self.providers:
        return None

    if provider_name in self.providers:
        return self.providers[provider_name]

    return None
```

### 2. 創建統一的 Helper 函數

**文件**：`backend/app/shared/llm_provider_helper.py`（新建）

**功能**：
- `get_provider_name_from_chat_model()`：從系統設置讀取 `chat_model` 並推斷 provider_name
- `get_llm_provider_from_settings()`：獲取 LLM provider（基於用戶配置，無 fallback）

**特點**：
- ✅ 從系統設置讀取 `chat_model`
- ✅ 從模型名稱推斷 provider（openai/anthropic/vertex-ai）
- ✅ 如果未配置或不可用，直接報錯
- ✅ 無任何 fallback 邏輯

### 3. 更新 `PlaybookRunner`

**文件**：`backend/app/services/playbook_runner.py`

**修改**：
- `_get_llm_provider()` 現在使用統一的 helper 函數
- 移除了所有 fallback 邏輯
- 如果 `chat_model` 未配置或 provider 不可用，直接報錯

---

## ✅ 已修復的調用點

以下文件中的 `get_provider()` 調用已全部修復，使用 `get_llm_provider_from_settings()`：

### 高優先級（核心功能）

1. **`backend/app/services/agent_runner.py:1091`** ✅
   - 修復：使用 `get_llm_provider_from_settings(self.llm_manager)`

2. **`backend/app/services/conversation/execution_coordinator.py:571, 610`** ✅
   - 修復：使用 `get_llm_provider_from_settings(llm_manager)`

3. **`backend/app/services/conversation/plan_builder.py:292, 295`** ✅
   - 修復：使用 `get_llm_provider_from_settings(llm_manager)`，移除所有 fallback 邏輯

4. **`backend/app/services/conversation/conversation_orchestrator.py:137, 591`** ✅
   - 修復：使用 `get_llm_provider_from_settings(llm_manager)`

5. **`backend/app/services/conversation_orchestrator.py:135, 584`** ✅
   - 修復：使用 `get_llm_provider_from_settings(llm_manager)`

### 中優先級（輔助功能）

6. **`backend/app/shared/llm_utils.py:130, 132`** ✅
   - 修復：使用 `get_llm_provider_from_settings(llm_provider)`，移除 fallback 邏輯

7. **`backend/app/services/conversation/context_builder.py:659`** ✅
   - 修復：使用 `get_llm_provider_from_settings(llm_manager)`

8. **`backend/app/services/conversation/cta_handler.py:973`** ✅
   - 修復：使用 `get_llm_provider_from_settings(llm_manager)`

### 低優先級（其他功能）

9. **`backend/features/mindscape/routes.py:524, 556, 834`** ✅
   - 修復：使用 `get_llm_provider_from_settings(agent_runner.llm_manager)`，添加錯誤處理

10. **`backend/app/services/execution_fallback_service.py:77`** ✅
    - 修復：使用 `get_llm_provider_from_settings(llm_provider)`

11. **`backend/app/services/playbook_optimization_service.py:133`** ✅
    - 修復：使用 `get_llm_provider_from_settings(llm_manager)`，添加錯誤處理

12. **`backend/app/services/backends/local_llm_backend.py:53`** ✅
    - 修復：使用 `get_llm_provider_from_settings(self.llm_manager)`

13. **`backend/app/shared/i18n_exporter.py:64`** ✅
    - 修復：使用 `get_llm_provider_from_settings(llm_manager)`
    - 同時修復導入錯誤：`backend.appshared.llm_utils` → `backend.app.shared.llm_utils`

---

## 🔧 修復模板

### 標準修復方法

**修復前**：
```python
llm_manager = self._get_llm_manager(profile_id)
provider = llm_manager.get_provider()  # ❌ 無 provider_name
```

**修復後**：
```python
from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings

llm_manager = self._get_llm_manager(profile_id)
provider = get_llm_provider_from_settings(llm_manager)  # ✅ 使用用戶配置
```

---

## 📋 驗證清單

修復完成後，驗證以下內容：

- [x] 所有 `get_provider()` 調用都指定了 `provider_name` 或使用 `get_llm_provider_from_settings()`
- [x] 沒有 `get_provider()` 無參數調用（已通過 grep 驗證）
- [x] 所有錯誤消息明確指出需要配置 `chat_model`
- [ ] 測試所有功能，確保在未配置 `chat_model` 時正確報錯
- [ ] 測試所有功能，確保在指定的 provider 不可用時正確報錯

---

## 🎯 預期行為

### 場景 1：用戶未配置 chat_model

**行為**：直接報錯
```
ValueError: chat_model not configured in system settings. Please configure chat_model in Settings.
```

### 場景 2：用戶配置了 chat_model，但對應的 provider 不可用

**行為**：直接報錯
```
ValueError: Selected provider 'openai' (from chat_model 'gpt-4o-mini') is not available.
Available providers: anthropic, vertex-ai.
Please configure the API key for 'openai' in Settings.
```

### 場景 3：用戶配置了 chat_model，provider 可用

**行為**：正常使用指定的 provider
```
[INFO] Using LLM provider 'anthropic' (from chat_model 'claude-3-5-sonnet-20241022')
```

---

## 📚 相關文件

- `backend/app/services/agent_runner.py` - LLMProviderManager 實現
- `backend/app/shared/llm_provider_helper.py` - 統一的 helper 函數（新建）
- `backend/app/services/playbook_runner.py` - 已修復
- `backend/app/services/suggestion_generator.py` - 參考實現（已正確實現）

---

**最後更新**：2025-12-04
**維護者**：Mindscape AI 開發團隊
**狀態**：✅ 所有修復完成

## 📝 修復摘要

**修復日期**：2025-12-04

**修復範圍**：
- 修復了 13 個文件中的 20 處無參數 `get_provider()` 調用
- 所有調用點已改為使用 `get_llm_provider_from_settings()`
- 移除了所有 fallback 邏輯
- 添加了適當的錯誤處理

**修復的文件列表**：
1. `backend/app/services/agent_runner.py` (1處)
2. `backend/app/services/conversation/execution_coordinator.py` (2處)
3. `backend/app/services/conversation/plan_builder.py` (2處，移除 fallback)
4. `backend/app/services/conversation/conversation_orchestrator.py` (2處)
5. `backend/app/services/conversation_orchestrator.py` (2處)
6. `backend/app/shared/llm_utils.py` (2處，移除 fallback)
7. `backend/app/services/conversation/context_builder.py` (1處)
8. `backend/app/services/conversation/cta_handler.py` (1處)
9. `backend/features/mindscape/routes.py` (3處)
10. `backend/app/services/execution_fallback_service.py` (1處)
11. `backend/app/services/playbook_optimization_service.py` (1處)
12. `backend/app/services/backends/local_llm_backend.py` (1處)
13. `backend/app/shared/i18n_exporter.py` (1處，同時修復導入錯誤)

**驗證結果**：
- ✅ 使用 `grep` 驗證：無任何無參數 `get_provider()` 調用
- ✅ 所有文件已添加必要的導入語句
- ✅ 錯誤處理已適當添加

