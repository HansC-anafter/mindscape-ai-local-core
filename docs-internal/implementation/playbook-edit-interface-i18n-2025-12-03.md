# Playbook 編輯介面多語系處理與架構優化

**日期**：2025-12-03
**狀態**：✅ 已完成

## 目標

1. 將 playbook 編輯介面的所有硬編碼中文文本統一替換為多語系（i18n）處理
2. 移除前端對硬編碼 metadata 的依賴，改為完全使用後端 API 返回的數據
3. 修復語言切換時數據被覆蓋的問題，確保側邊欄和標題能正確切換語言

## 實作範圍

### 修改的檔案

#### 前端檔案

1. **PlaybookTabs.tsx** (`web-console/src/components/playbook/PlaybookTabs.tsx`)
   - 替換所有硬編碼的中文文本為 i18n 調用
   - 添加 `useLocale` hook 以支援日期格式化的多語系

2. **page.tsx** (`web-console/src/app/playbooks/[code]/page.tsx`)
   - 移除對 `getPlaybookMetadata` 的依賴
   - 改為直接使用後端 API 返回的數據
   - 修復輪詢邏輯，添加 `locale` 依賴
   - 優化 `loadPlaybookStatus` 更新邏輯，確保不覆蓋 metadata

3. **PlaybookInfo.tsx** (`web-console/src/components/playbook/PlaybookInfo.tsx`)
   - 移除對 `getPlaybookMetadata` 的依賴
   - 改為直接使用後端 API 返回的數據

4. **i18n 語言檔案**
   - `web-console/src/lib/i18n/locales/playbooks/zh-TW.ts`
   - `web-console/src/lib/i18n/locales/playbooks/en.ts`
   - `web-console/src/lib/i18n/locales/playbooks/ja.ts`

#### 後端檔案

5. **playbook.py** (`backend/app/routes/core/playbook.py`)
   - 修復 `get_playbook` API 的 locale 處理，添加 'ja' 語言支持
   - 優化 `list_playbooks` 的語言選擇邏輯，確保優先選擇匹配 `preferred_locale` 的版本

## 新增的 i18n 鍵

### 關聯意圖相關

1. **noAssociatedIntents** - 尚未關聯任何長期意圖
2. **createIntentInMindscape** - 可以在「心智空間」中建立意圖並關聯到此 Playbook

### 個人版本相關

3. **letLLMCreatePersonalVersion** - 讓 LLM 根據我的使用情境，做一份個人版本
4. **youAlreadyHavePersonalVersion** - 你已經有個人版本了。可以重新用 LLM 調整：

### 執行記錄相關

5. **executingWithCount** - 執行中 ({count})
6. **executionId** - 執行 ID
7. **status** - 狀態
8. **startedAt** - 開始時間
9. **inProgress** - 🔄 進行中
10. **recentExecutionHistory** - 最近執行記錄
11. **started** - 開始
12. **completedLabel** - 完成（標籤用，避免與現有的 completed 鍵衝突）

### 錯誤訊息相關

13. **executionFailedWithError** - 執行失敗：{error}

### 其他

14. **times** - 次（用於使用次數顯示）

## 架構改進

### 移除硬編碼 Metadata 依賴

**問題**：前端使用 `getPlaybookMetadata` 作為 fallback，這會導致：
- 用戶自定義的 playbook 無法正確顯示（因為前端 metadata 中沒有）
- 維護成本高，每次新增 playbook 都需要更新前端 metadata

**解決方案**：
- 完全移除對 `getPlaybookMetadata` 的依賴
- 直接使用後端 API 返回的 `playbook.metadata` 數據
- 後端根據 `target_language` 參數返回對應語言版本的數據

**修改位置**：
- `web-console/src/app/playbooks/[code]/page.tsx:463-466`
- `web-console/src/components/playbook/PlaybookInfo.tsx:172-175`

### 修復語言切換問題

**問題**：切換語言時，側邊欄和標題會先變成英文，然後又變回中文

**原因**：
1. 輪詢的 `useEffect` 沒有將 `locale` 作為依賴
2. 當語言切換時，舊的輪詢 interval 仍在使用舊的 `locale` 值
3. 輪詢請求使用舊語言，返回中文數據，可能覆蓋 metadata

**解決方案**：
1. 在輪詢的 `useEffect` 中添加 `locale` 依賴（`web-console/src/app/playbooks/[code]/page.tsx:139`）
2. 優化 `loadPlaybookStatus` 更新邏輯，明確只更新 `execution_status` 和 `version_info`，不覆蓋 metadata（`web-console/src/app/playbooks/[code]/page.tsx:221-233`）

### 後端語言選擇邏輯優化

**問題**：後端 `list_playbooks` 在選擇語言版本時，如果先遇到中文版本，會先放入字典，即使後面有英文版本也可能不會替換

**解決方案**：
- 優化語言選擇邏輯，確保優先選擇匹配 `preferred_locale` 的版本
- 添加 'ja' 語言支持（`backend/app/routes/core/playbook.py:268-269`）

## 實作細節

### PlaybookTabs.tsx 修改

#### 1. 添加 useLocale hook

```typescript
import { t, useLocale } from '../../lib/i18n';

export default function PlaybookTabs({...}: PlaybookTabsProps) {
  const [locale] = useLocale();
  // ...
}
```

#### 2. 替換硬編碼文本

- 關聯意圖空狀態訊息（第 141-142 行）
- 個人版本建立按鈕文字（第 191 行）
- 個人版本已存在提示（第 197 行）
- 執行中標題（第 217 行）
- 執行記錄相關標籤（第 224, 227, 231, 236, 245, 251, 266, 269 行）
- 無執行記錄訊息（第 283, 290-291 行）

#### 3. 日期格式化多語系

將日期格式化從硬編碼的 `'zh-TW'` 改為根據當前語言動態選擇：

```typescript
new Date(exec.started_at).toLocaleString(
  locale === 'en' ? 'en-US' :
  locale === 'ja' ? 'ja-JP' :
  'zh-TW'
)
```

### page.tsx 修改

#### 1. 移除硬編碼 metadata 依賴

```typescript
// 移除
import { getPlaybookMetadata } from '../../../lib/i18n/locales/playbooks';

// 改為直接使用後端數據
const playbookName = playbook.metadata.name;
const playbookDescription = playbook.metadata.description;
const playbookTags = playbook.metadata.tags || [];
```

#### 2. 修復輪詢邏輯

```typescript
// 添加 locale 依賴
useEffect(() => {
  if (!playbookCode) return;
  const interval = setInterval(() => {
    loadPlaybookStatus();
  }, 5000);
  return () => clearInterval(interval);
}, [playbookCode, locale]); // 添加 locale 依賴
```

#### 3. 優化 loadPlaybookStatus 更新邏輯

```typescript
setPlaybook(prev => {
  if (!prev) {
    return data;
  }
  // Only update execution_status and version_info, preserve metadata from initial load
  return {
    ...prev,
    execution_status: data.execution_status,
    version_info: data.version_info
  };
});
```

### 後端 API 修改

#### 1. 添加 'ja' 語言支持

```python
elif target_language.startswith('ja') or target_language == 'ja':
    preferred_locale = 'ja'
```

#### 2. 優化語言選擇邏輯

確保優先選擇匹配 `preferred_locale` 的版本，如果都不匹配，按優先級（zh-TW > en > ja）選擇。

## 語言檔案更新

### 繁體中文 (zh-TW.ts)

所有新增鍵的繁體中文翻譯已添加到 `playbooksZhTW` 物件中。

### 英文 (en.ts)

所有新增鍵的英文翻譯已添加到 `playbooksEn` 物件中。

### 日文 (ja.ts)

所有新增鍵的日文翻譯已添加到 `playbooksJa` 物件中。

## 驗證

- [x] 所有硬編碼中文文本已替換為 i18n 調用
- [x] 三個語言檔案都已添加對應的翻譯鍵
- [x] 日期格式化支援多語系
- [x] 移除前端硬編碼 metadata 依賴
- [x] 修復語言切換問題
- [x] 後端正確處理多語系請求
- [x] 無 lint 錯誤
- [x] 程式碼符合專案規範（英文註釋，無中文註釋、實作步驟、非功能性描述、emoji）

## 相關檔案路徑

### 前端檔案

- `web-console/src/components/playbook/PlaybookTabs.tsx:1-300`
- `web-console/src/app/playbooks/[code]/page.tsx:8, 139, 142-161, 163-203, 205-230, 463-466`
- `web-console/src/components/playbook/PlaybookInfo.tsx:4-5, 172-175`
- `web-console/src/lib/i18n/locales/playbooks/zh-TW.ts:164-178`
- `web-console/src/lib/i18n/locales/playbooks/en.ts:164-178`
- `web-console/src/lib/i18n/locales/playbooks/ja.ts:164-178`

### 後端檔案

- `backend/app/routes/core/playbook.py:56-89, 260-275`

## 備註

- `completedLabel` 鍵名使用 `Label` 後綴以避免與現有的 `completed` 鍵衝突
- 日期格式化使用 `toLocaleString` 並根據當前語言選擇對應的 locale
- 所有新增的 i18n 鍵都遵循現有的命名規範
- Playbook 數據完全由後端管理，前端不再依賴硬編碼 metadata
- 支援系統預設和用戶自定義的 playbook
- 語言切換時，輪詢會自動使用新的語言參數
