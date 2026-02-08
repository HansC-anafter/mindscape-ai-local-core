---
playbook_code: page_sections
version: 1.0.0
capability_code: web_generation
name: 網頁 Sections 生成
description: 讀取頁面規格文檔，為每個 section 生成 React 組件
tags:
  - web
  - code-generation
  - react
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

entry_agent_type: coder
icon: 🧩
---

# 網頁 Sections 生成 - SOP

## 目標
讀取 `spec/page.md` 頁面規格文檔，為每個 section 生成 React 組件，輸出到 Project Sandbox 的 `sections/` 目錄。

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.1: 檢查是否有活躍的 web_page project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page`
- 如果沒有，提示用戶需要先創建 web_page project

#### 步驟 0.2: 獲取 Project Sandbox 路徑
- 使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/web_page/{project_id}/`
- 確保 `sections/` 目錄存在

#### 步驟 0.3: 讀取頁面規格文檔
- 讀取 `spec/page.md`（從 `page_outline` playbook 生成）
- 如果不存在，提示用戶需要先執行 `page_outline` playbook
- 解析頁面規格，提取 sections 列表

### Phase 1: 解析頁面規格

#### 步驟 1.1: 讀取 `spec/page.md`
**必須**使用 `filesystem_read_file` 工具讀取頁面規格文檔：

- **文件路徑**：`spec/page.md`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/web_page/{project_id}/spec/page.md`

#### 步驟 1.2: 解析 Sections 列表
從 `page.md` 中提取：
- 所有 sections 的列表（About、Features、Content、Contact 等）
- 每個 section 的內容要點
- 每個 section 的佈局方式
- 每個 section 的視覺元素需求

#### 步驟 1.3: 提取樣式規範
從 `page.md` 中提取：
- 色彩方案（主色、次色、強調色）
- 字體建議
- 視覺風格
- 交互設計要求

### Phase 2: 生成 Section 組件

#### 步驟 2.1: About Section 組件
如果頁面規格中包含 About Section：

- **組件名稱**：`About.tsx`
- **輸出路徑**：`sections/About.tsx`
- **組件內容**：
  - 根據 page.md 中的 About Section 內容要點生成
  - 使用統一的樣式規範（從 page.md 提取）
  - 實現響應式設計
  - 包含適當的視覺元素（圖片、圖標等）

**組件結構範例**：
```typescript
import React from 'react'

interface AboutProps {
  // Props based on page.md specification
}

export default function About({ ...props }: AboutProps) {
  return (
    <section className="about-section">
      {/* Content based on page.md */}
    </section>
  )
}
```

#### 步驟 2.2: Features Section 組件
如果頁面規格中包含 Features Section：

- **組件名稱**：`Features.tsx`
- **輸出路徑**：`sections/Features.tsx`
- **組件內容**：
  - 根據 page.md 中的特色項目列表生成
  - 使用指定的展示方式（卡片、列表、時間軸等）
  - 實現互動效果（如果指定）
  - 使用統一的樣式規範

#### 步驟 2.3: Content Section 組件
如果頁面規格中包含 Content Section：

- **組件名稱**：`Content.tsx`
- **輸出路徑**：`sections/Content.tsx`
- **組件內容**：
  - 根據 page.md 中的內容結構生成
  - 支持指定的內容類型（文章、圖片、影片等）
  - 實現適當的展示方式

#### 步驟 2.4: Contact Section 組件
如果頁面規格中包含 Contact Section：

- **組件名稱**：`Contact.tsx`
- **輸出路徑**：`sections/Contact.tsx`
- **組件內容**：
  - 根據 page.md 中的聯絡資訊生成
  - 實現表單（如果指定）
  - 包含社交媒體連結（如果指定）
  - 使用統一的樣式規範

#### 步驟 2.5: 其他 Sections
根據 page.md 中定義的其他 sections，生成對應的組件：
- 每個 section 一個組件文件
- 組件名稱使用 PascalCase
- 確保所有組件使用統一的樣式規範

### Phase 3: 樣式一致性處理

#### 步驟 3.1: 創建共享樣式文件（可選）
如果需要，創建共享樣式文件：

- **文件路徑**：`sections/styles.ts` 或 `sections/styles.css`
- **內容**：統一的樣式定義（色彩、字體、間距等）
- 所有 section 組件都引用這個文件

#### 步驟 3.2: 確保組件風格一致
- 所有組件使用相同的色彩方案
- 所有組件使用相同的字體
- 所有組件使用相同的間距和佈局規則
- 所有組件實現響應式設計

### Phase 4: 組件輸出與保存

#### 步驟 4.1: 保存所有 Section 組件
**必須**使用 `filesystem_write_file` 工具保存每個 section 組件：

- **About.tsx**：`sections/About.tsx`
- **Features.tsx**：`sections/Features.tsx`
- **Content.tsx**：`sections/Content.tsx`
- **Contact.tsx**：`sections/Contact.tsx`
- 其他 sections...

#### 步驟 4.2: 註冊 Artifacts
**必須**使用 `artifact_registry.register_artifact` 註冊產出的 artifacts：

- **artifact_id**：`sections`
- **artifact_type**：`react_components`
- **path**：`sections/`
- **metadata**：
  - `components`：組件列表（["About.tsx", "Features.tsx", ...]）
  - `count`：組件數量
  - `created_at`：創建時間

### Phase 5: 執行記錄保存

#### 步驟 5.1: 保存對話歷史
**必須**使用 `filesystem_write_file` 工具保存完整的對話歷史：

- 文件路徑: `artifacts/page_sections/{{execution_id}}/conversation_history.json`
- 內容: 完整的對話歷史（包含所有 user 和 assistant 消息）
- 格式: JSON 格式，包含時間戳和角色信息

#### 步驟 5.2: 保存執行摘要
**必須**使用 `filesystem_write_file` 工具保存執行摘要：

- 文件路徑: `artifacts/page_sections/{{execution_id}}/execution_summary.md`
- 內容:
  - 執行時間
  - 執行 ID
  - Playbook 名稱
  - 讀取的頁面規格文檔路徑
  - 生成的組件列表
  - 執行結果摘要

## 個人化

基於使用者的 Mindscape 個人檔案：
- **技術等級**：若為「進階」，包含更多技術細節和自訂選項
- **詳細程度**：若偏好「高」，提供更詳細的組件實現
- **工作風格**：若偏好「結構化」，提供更清晰的組件結構

## 與長期意圖的整合

若使用者有相關的活躍意圖（例如「建立公司登陸頁面」），明確引用：
> "由於您正在進行「建立公司登陸頁面」，我將根據頁面規格為您生成所有必要的 section 組件..."

## 成功標準

- 所有 section 組件已生成到 Project Sandbox 的 `sections/` 目錄
- 組件根據 `spec/page.md` 中的規劃生成
- 所有組件使用統一的樣式規範
- 組件實現響應式設計
- Artifacts 已正確註冊
- 組件可以直接在 React 項目中使用

## 注意事項

- **依賴關係**：必須先執行 `page_outline` playbook 生成 `spec/page.md`
- **Project Context**：必須在 web_page project 的 context 中執行
- **樣式一致性**：確保所有組件使用相同的樣式規範（從 page.md 提取）
- **組件命名**：使用 PascalCase，與 React 慣例一致
- **響應式設計**：所有組件都應該實現響應式設計

