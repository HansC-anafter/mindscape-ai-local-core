---
playbook_code: page_outline
version: 1.0.0
capability_code: web_generation
name: 網頁結構規劃
description: 分析用戶需求，規劃頁面結構（sections、layout、內容方向），生成頁面規格文檔
tags:
  - web
  - planning
  - design
  - frontend

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - filesystem_write_file
  - filesystem_read_file

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 📋
---

# 網頁結構規劃 - SOP

## 目標
分析用戶需求，規劃頁面結構（sections、layout、內容方向），生成 `spec/page.md` 頁面規格文檔到 Project Sandbox。

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.1: 檢查是否有活躍的 web_page project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page`
- 如果沒有，提示用戶需要先創建 web_page project

#### 步驟 0.2: 獲取 Project Sandbox 路徑
- 使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/web_page/{project_id}/`
- 確保 `spec/` 目錄存在

### Phase 1: 需求收集

#### 步驟 1.1: 頁面主題與目標
- **主題**：詢問頁面的主題或主題（例如：「城市覺知」、「產品介紹」、「個人作品集」）
- **目標**：了解頁面的主要目標（展示、轉換、教育、品牌形象等）
- **目標受眾**：識別目標受眾（一般用戶、專業人士、潛在客戶等）

#### 步驟 1.2: 內容方向
- **核心訊息**：識別需要傳達的核心訊息
- **內容類型**：確定內容類型（文字、圖片、影片、互動元素等）
- **風格偏好**：了解設計風格偏好（現代、極簡、復古、科技感等）

#### 步驟 1.3: 功能需求
- **互動需求**：是否需要互動元素（表單、動畫、3D 效果等）
- **響應式需求**：行動裝置適配需求
- **效能需求**：效能限制與目標裝置

### Phase 2: 頁面結構設計

#### 步驟 2.1: Hero 區塊規劃
- **Hero 類型**：確定 hero 區塊類型（Three.js 互動、靜態圖片、影片背景等）
- **Hero 內容**：規劃 hero 區塊的主要內容（標題、副標題、CTA 按鈕等）
- **Hero 風格**：定義 hero 區塊的視覺風格和動畫效果

#### 步驟 2.2: Sections 規劃
為頁面規劃各個 section：

- **About Section**（關於區塊）
  - 內容要點
  - 視覺元素（圖片、圖標等）
  - 佈局方式（單欄、雙欄、網格等）

- **Features Section**（特色區塊）
  - 特色項目列表
  - 展示方式（卡片、列表、時間軸等）
  - 互動效果

- **Content Section**（內容區塊）
  - 內容類型（文章、圖片、影片等）
  - 內容結構
  - 展示方式

- **Contact Section**（聯絡區塊）
  - 聯絡方式
  - 表單設計
  - 社交媒體連結

- **Footer**（頁尾）
  - 頁尾內容
  - 連結結構
  - 版權資訊

#### 步驟 2.3: 導航與佈局
- **導航結構**：規劃導航菜單結構
- **頁面佈局**：確定整體佈局方式（單頁、多頁、分區等）
- **響應式設計**：規劃不同螢幕尺寸的佈局適配

### Phase 3: 內容大綱規劃

#### 步驟 3.1: 各 Section 內容要點
為每個 section 規劃具體的內容要點：

- **Hero Section**
  - 主標題
  - 副標題
  - CTA 按鈕文字
  - 背景元素描述

- **About Section**
  - 關於內容要點（3-5 個重點）
  - 視覺元素需求

- **Features Section**
  - 特色項目列表（每個項目的標題和描述）
  - 圖標或圖片需求

- **Content Section**
  - 內容段落結構
  - 圖片或影片需求

- **Contact Section**
  - 聯絡資訊
  - 表單欄位

#### 步驟 3.2: 內容優先級
- 確定內容的優先級（哪些是核心訊息，哪些是次要資訊）
- 規劃內容的展示順序

### Phase 4: 樣式和交互設計建議

#### 步驟 4.1: 視覺風格定義
- **色彩方案**：定義主要色彩、次要色彩、強調色
- **字體選擇**：建議字體家族和字體大小
- **視覺元素**：圖標風格、圖片風格、動畫風格

#### 步驟 4.2: 交互設計
- **動畫效果**：規劃頁面動畫效果（滾動觸發、懸停效果等）
- **互動元素**：定義互動元素的行為（按鈕、表單、導航等）
- **使用者體驗**：確保良好的使用者體驗流程

### Phase 5: 生成頁面規格文檔

#### 步驟 5.1: 生成 `spec/page.md`
**必須**使用 `filesystem_write_file` 工具保存頁面規格文檔：

- **文件路徑**：`spec/page.md`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/web_page/{project_id}/spec/page.md`

**文檔結構**：
```markdown
# 頁面規格：{頁面標題}

## 頁面資訊
- **主題**：{主題}
- **目標**：{目標}
- **目標受眾**：{目標受眾}

## Hero 區塊
- **類型**：{hero 類型}
- **內容**：
  - 主標題：{主標題}
  - 副標題：{副標題}
  - CTA：{CTA 文字}
- **風格**：{風格描述}

## Sections 規劃

### About Section
- **內容要點**：
  - {要點 1}
  - {要點 2}
- **佈局**：{佈局方式}
- **視覺元素**：{視覺元素需求}

### Features Section
- **特色項目**：
  - {項目 1}：{描述}
  - {項目 2}：{描述}
- **展示方式**：{展示方式}

### Content Section
- **內容結構**：{內容結構}
- **內容類型**：{內容類型}

### Contact Section
- **聯絡方式**：{聯絡方式}
- **表單欄位**：{表單欄位}

## 樣式規範
- **色彩方案**：
  - 主色：{主色}
  - 次色：{次色}
  - 強調色：{強調色}
- **字體**：{字體建議}
- **視覺風格**：{視覺風格}

## 交互設計
- **動畫效果**：{動畫效果}
- **互動元素**：{互動元素}
```

#### 步驟 5.2: 註冊 Artifact
**必須**使用 `artifact_registry.register_artifact` 註冊產出的 artifact：

- **artifact_id**：`page_spec`
- **artifact_type**：`markdown`
- **path**：`spec/page.md`
- **metadata**：
  - `page_title`：頁面標題
  - `sections`：sections 列表
  - `created_at`：創建時間

### Phase 6: 執行記錄保存

#### 步驟 6.1: 保存對話歷史
**必須**使用 `filesystem_write_file` 工具保存完整的對話歷史：

- 文件路徑: `artifacts/page_outline/{{execution_id}}/conversation_history.json`
- 內容: 完整的對話歷史（包含所有 user 和 assistant 消息）
- 格式: JSON 格式，包含時間戳和角色信息

#### 步驟 6.2: 保存執行摘要
**必須**使用 `filesystem_write_file` 工具保存執行摘要：

- 文件路徑: `artifacts/page_outline/{{execution_id}}/execution_summary.md`
- 內容:
  - 執行時間
  - 執行 ID
  - Playbook 名稱
  - 主要輸入參數（頁面主題、目標、內容方向等）
  - 執行結果摘要
  - 生成的頁面規格文檔路徑

## 個人化

基於使用者的 Mindscape 個人檔案：
- **技術等級**：若為「進階」，包含更多技術細節和自訂選項
- **詳細程度**：若偏好「高」，提供更詳細的規劃和建議
- **工作風格**：若偏好「結構化」，提供更清晰的結構和步驟

## 與長期意圖的整合

若使用者有相關的活躍意圖（例如「建立公司登陸頁面」），明確引用：
> "由於您正在進行「建立公司登陸頁面」，我將專注於創建與您的品牌識別和轉換目標一致的頁面結構..."

## 成功標準

- 頁面規格文檔已生成到 Project Sandbox 的 `spec/page.md`
- 文檔包含完整的頁面結構規劃
- 所有 sections 都有清晰的內容要點
- 樣式和交互設計建議已包含
- Artifact 已正確註冊
- 文檔格式清晰，易於後續 playbook 使用

## 注意事項

- **Project Context**：必須在 web_page project 的 context 中執行
- **Sandbox 路徑**：確保使用 Project Sandbox 路徑，而非 artifacts 路徑
- **文檔格式**：使用 Markdown 格式，確保結構清晰
- **向後兼容**：如果沒有 project context，可以降級到 artifacts 路徑（但會提示用戶）

