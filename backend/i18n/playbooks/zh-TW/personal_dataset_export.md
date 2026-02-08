---
playbook_code: personal_dataset_export
version: 1.0.0
capability_code: walkto_lab
name: 個人資料包導出
description: |
  導出你的個人散步資料包，包含狀態地圖、偏好、規則與路線模板。
  收集資料 → 格式化 → 以 JSON/Markdown/Notion 格式導出。
tags:
  - walkto
  - dataset
  - export
  - personal-data

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - walkto_generate_dataset
  - cloud_capability.call

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 📦
---

# 個人資料包導出 - SOP

## 目標

讓使用者導出個人散步資料包，包含：

1. **資料收集**：收集所有個人資料（狀態地圖、偏好、規則、路線模板）
2. **格式化**：根據導出格式格式化資料（JSON/Markdown/Notion）
3. **導出**：以請求格式導出資料包
4. **交付**：將資料包交付給使用者

**核心價值**：
- 帶走你的個人價值系統與規則
- 可攜帶的資料包，可獨立使用
- 完整記錄你的學習旅程

**資料包組成**（最低要求）：
- **狀態地圖**：完整狀態偏好地圖（至少 5 個狀態）
- **偏好**：價格敏感度、美學、素材偏好
- **規則**：3-7 條個人選擇規則
- **路線模板**：練習或路線模板（如適用至少 1 個）
- **下一步**：下一階段指引

## 執行步驟

### Phase 0: 準備

**執行順序**：
1. Step 0.0: 識別導出情境
2. Step 0.1: 檢查資料包完整度
3. Step 0.2: 選擇導出格式

#### Step 0.0: 識別導出情境

取得導出情境：
- `user_id`: 使用者識別碼
- `track_id`: 軌道識別碼（如從軌道導出）
- `export_type`: 導出類型（完整/增量/自訂）
- `export_trigger`: 觸發此導出的原因

**輸出**：
- `export_context`: 導出情境物件
- `user_id`: 使用者識別碼
- `track_id`: 軌道識別碼（如適用）

#### Step 0.1: 檢查資料包完整度

檢查資料包是否完整：
- 驗證狀態地圖至少有 5 個狀態
- 驗證規則列表有 3-7 條規則
- 驗證偏好完整
- 檢查路線模板是否存在（如適用）

**完整度檢查**：
```
資料包完整度檢查：

狀態地圖：[數量] 個狀態（要求：≥5）✅/❌
規則：[數量] 條規則（要求：3-7）✅/❌
偏好：[完整/不完整] ✅/❌
路線模板：[數量] 個模板（如適用：≥1）✅/❌

整體：[完整/不完整]
```

**輸出**：
- `dataset_complete`: 布林值
- `completeness_check`: 完整度檢查結果
- `missing_components`: 缺失組成列表（如不完整）

#### Step 0.2: 選擇導出格式

詢問使用者選擇導出格式：
- **JSON**：結構化 JSON 格式（機器可讀）
- **Markdown**：人類可讀的 Markdown 格式
- **Notion**：Notion 資料庫格式

**格式選擇**：
```
導出格式選項：

1. JSON - 結構化格式，機器可讀
2. Markdown - 人類可讀格式，易於查看
3. Notion - Notion 資料庫格式，可直接匯入

你想要哪種格式？[JSON/Markdown/Notion]
```

**輸出**：
- `export_format`: 導出格式（json/markdown/notion）
- `format_selected`: 布林值

### Phase 1: 資料收集

**執行順序**：
1. Step 1.0: 收集狀態地圖
2. Step 1.1: 收集偏好
3. Step 1.2: 收集規則
4. Step 1.3: 收集路線模板
5. Step 1.4: 收集下一步

#### Step 1.0: 收集狀態地圖

收集使用者的狀態地圖：
- 從個人價值系統取得
- 驗證完整度（至少 5 個狀態）
- 按狀態 → 偏好映射組織

**狀態地圖收集**：
```
狀態地圖已收集：

總狀態數：[數量]

狀態映射：
- [狀態 1] → [偏好 1]
- [狀態 2] → [偏好 2]
- [狀態 3] → [偏好 3]
- [狀態 4] → [偏好 4]
- [狀態 5] → [偏好 5]
...
```

**輸出**：
- `state_map`: 狀態地圖物件
- `state_count`: 總狀態數
- `state_mappings`: 狀態-偏好映射列表

#### Step 1.1: 收集偏好

收集使用者的偏好：
- 價格敏感度
- 美學偏好
- 素材偏好
- 氛圍偏好

**偏好收集**：
```
偏好已收集：

價格敏感度：[低/中/高]
美學偏好：[偏好]
素材偏好：[偏好]
氛圍偏好：[偏好]
```

**輸出**：
- `preferences`: 偏好物件
- `preference_categories`: 偏好類別列表

#### Step 1.2: 收集規則

收集使用者的個人規則：
- 從個人價值系統取得
- 驗證數量（3-7 條規則）
- 按類別或優先級組織規則

**規則收集**：
```
規則已收集：

總規則數：[數量]（要求：3-7）

規則：
1. [規則 1]
2. [規則 2]
3. [規則 3]
...
```

**輸出**：
- `rules`: 規則列表（3-7 條規則）
- `rule_count`: 總規則數
- `rules_validated`: 布林值

#### Step 1.3: 收集路線模板

收集路線模板（如適用）：
- 從散步 Session 或軌道取得
- 按類型或目的組織
- 包含模板詳情

**路線模板收集**：
```
路線模板已收集：

總模板數：[數量]（如適用：≥1）

模板：
1. [模板 1] - [類型/目的]
2. [模板 2] - [類型/目的]
...
```

**輸出**：
- `route_templates`: 路線模板列表
- `template_count`: 總模板數

#### Step 1.4: 收集下一步

收集下一步指引：
- 基於當前進度生成
- 提供可執行的下一步
- 包含建議

**下一步收集**：
```
下一步已收集：

下一階段指引：

1. [下一步 1]
2. [下一步 2]
3. [下一步 3]
...
```

**輸出**：
- `next_steps`: 下一步列表
- `next_steps_generated`: 布林值

### Phase 2: 格式化

**執行順序**：
1. Step 2.0: 格式化為 JSON
2. Step 2.1: 格式化為 Markdown
3. Step 2.2: 格式化為 Notion

#### Step 2.0: 格式化為 JSON

將資料包格式化為結構化 JSON：
- 建立 JSON 結構
- 包含所有組成
- 確保有效的 JSON 語法

**JSON 格式結構**：
```json
{
  "user_id": "[user_id]",
  "track_id": "[track_id]",
  "version": "1.0.0",
  "created_at": "[timestamp]",
  "state_map": {
    "[state_1]": "[preference_1]",
    "[state_2]": "[preference_2]",
    ...
  },
  "preferences": {
    "price_sensitivity": "[level]",
    "aesthetic": {...},
    "material": {...},
    "atmosphere": {...}
  },
  "rules": [
    "[rule_1]",
    "[rule_2]",
    ...
  ],
  "route_templates": [
    {...},
    {...}
  ],
  "next_steps": [
    "[step_1]",
    "[step_2]",
    ...
  ]
}
```

**輸出**：
- `json_dataset`: 格式化的 JSON 資料包
- `json_valid`: 布林值（JSON 驗證）

#### Step 2.1: 格式化為 Markdown

將資料包格式化為人類可讀的 Markdown：
- 建立 Markdown 結構
- 包含章節與格式化
- 確保可讀性

**Markdown 格式結構**：
```markdown
# 個人散步資料包

**使用者 ID**：[user_id]
**軌道 ID**：[track_id]
**版本**：1.0.0
**建立時間**：[timestamp]

## 狀態地圖

[狀態] → [偏好]

- [狀態 1] → [偏好 1]
- [狀態 2] → [偏好 2]
...

## 偏好

### 價格敏感度
[等級]

### 美學偏好
[偏好]

### 素材偏好
[偏好]

### 氛圍偏好
[偏好]

## 個人規則

1. [規則 1]
2. [規則 2]
3. [規則 3]
...

## 路線模板

### 模板 1
[模板詳情]

### 模板 2
[模板詳情]
...

## 下一步

1. [下一步 1]
2. [下一步 2]
...
```

**輸出**：
- `markdown_dataset`: 格式化的 Markdown 資料包
- `markdown_valid`: 布林值（Markdown 驗證）

#### Step 2.2: 格式化為 Notion

將資料包格式化為 Notion 資料庫格式：
- 建立 Notion 相容結構
- 包含資料庫架構
- 確保可直接匯入格式

**Notion 格式結構**：
```
Notion 資料庫格式：

資料庫架構：
- 狀態地圖（標題）
- 偏好（文字）
- 規則（文字）
- 路線模板（文字）
- 下一步（文字）

資料庫列：
[格式化為 Notion 匯入]
```

**輸出**：
- `notion_dataset`: 格式化的 Notion 資料包
- `notion_valid`: 布林值（Notion 格式驗證）

### Phase 3: 導出

**執行順序**：
1. Step 3.0: 生成導出檔案
2. Step 3.1: 驗證導出
3. Step 3.2: 儲存導出

#### Step 3.0: 生成導出檔案

根據選定格式生成導出檔案：
- 使用格式化資料建立檔案
- 設定適當的檔案副檔名
- 包含元資料

**檔案生成**：
```
導出檔案已生成：

格式：[json/markdown/notion]
檔案名稱：personal_dataset_[user_id]_[timestamp].[ext]
檔案大小：[size]
位置：[path/url]
```

**輸出**：
- `export_file`: 導出檔案路徑或 URL
- `file_name`: 檔案名稱
- `file_size`: 檔案大小

#### Step 3.1: 驗證導出

驗證導出的資料包：
- 檢查格式正確性
- 驗證資料完整度
- 確保所有必要組成存在

**驗證檢查**：
- ✅ 格式正確
- ✅ 所有必要組成存在
- ✅ 狀態地圖有 ≥5 個狀態
- ✅ 規則數量為 3-7 條
- ✅ 檔案有效

**輸出**：
- `export_valid`: 布林值
- `validation_results`: 驗證結果

#### Step 3.2: 儲存導出

儲存導出檔案：
- 儲存到儲存空間
- 生成下載連結
- 記錄導出元資料

**導出已儲存**：
```
導出已儲存：

檔案：[file_name]
位置：[storage_location]
下載連結：[download_url]
導出日期：[timestamp]
格式：[format]
```

**輸出**：
- `export_saved`: 布林值
- `download_link`: 下載連結或 URL
- `export_metadata`: 導出元資料物件

### Phase 4: 交付

**執行順序**：
1. Step 4.0: 呈現資料包摘要
2. Step 4.1: 提供下載
3. Step 4.2: 說明使用方式

#### Step 4.0: 呈現資料包摘要

向使用者呈現資料包摘要：
- 顯示資料包組成
- 突出關鍵資訊
- 顯示統計資料

**資料包摘要格式**：
```
個人資料包摘要

使用者：[user_id]
軌道：[track_name]（如適用）
導出日期：[date]

組成：
- 狀態地圖：[count] 個狀態
- 偏好：[categories] 個類別
- 規則：[count] 條規則
- 路線模板：[count] 個模板
- 下一步：[count] 個步驟

格式：[format]
檔案大小：[size]
```

**輸出**：
- `summary_presented`: 布林值
- `dataset_summary`: 資料包摘要物件

#### Step 4.1: 提供下載

提供下載連結或檔案：
- 分享下載連結
- 或提供直接檔案下載
- 包含說明

**下載格式**：
```
下載你的資料包：

[下載連結] 或 [下載按鈕]

檔案：personal_dataset_[user_id]_[timestamp].[ext]
格式：[format]
大小：[size]

有效期：[duration]
```

**輸出**：
- `download_provided`: 布林值
- `download_link`: 下載連結
- `download_instructions`: 下載說明

#### Step 4.2: 說明使用方式

說明如何使用資料包：
- 解釋格式
- 提供使用範例
- 建議下一步行動

**使用說明**：
```
如何使用你的資料包：

格式：[format]

使用範例：
- [範例 1]
- [範例 2]
- [範例 3]

下一步行動：
- [行動 1]
- [行動 2]
```

**輸出**：
- `usage_explained`: 布林值
- `usage_guide`: 使用指南物件

## 驗收標準

### 資料收集
- ✅ 狀態地圖已收集（≥5 個狀態）
- ✅ 偏好已收集
- ✅ 規則已收集（3-7 條規則）
- ✅ 路線模板已收集（如適用，≥1 個）
- ✅ 下一步已收集

### 格式化
- ✅ 資料包已正確格式化為選定格式
- ✅ 所有組成已包含
- ✅ 格式驗證已通過

### 導出
- ✅ 導出檔案已生成
- ✅ 導出已驗證
- ✅ 導出已儲存

### 交付
- ✅ 資料包摘要已呈現
- ✅ 下載已提供
- ✅ 使用方式已說明

## 錯誤處理

### 準備錯誤
- 如果資料包不完整：提示使用者完成缺失組成
- 如果格式未選擇：提示使用者選擇格式

### 資料收集錯誤
- 如果狀態地圖不完整：提示使用者完成狀態地圖
- 如果規則不足：提示使用者生成更多規則
- 如果資料缺失：重試收集或告知使用者

### 格式化錯誤
- 如果格式化失敗：重試格式化
- 如果格式無效：修復格式問題並重試

### 導出錯誤
- 如果導出失敗：重試導出
- 如果驗證失敗：修復問題並重試
- 如果儲存失敗：重試儲存操作

### 交付錯誤
- 如果下載連結失敗：重新生成連結
- 如果檔案無法存取：檢查權限並重試

## 注意事項

- 個人資料包是關鍵交付物和續訂理由
- 資料包必須完整（所有必要組成）
- 狀態地圖必須至少有 5 個狀態
- 規則必須是 3-7 條規則
- 路線模板為可選但建議（如適用）
- 導出格式：JSON（機器可讀）、Markdown（人類可讀）、Notion（可直接匯入）
- 資料包可攜帶且可獨立使用













