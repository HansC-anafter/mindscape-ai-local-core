---
playbook_code: obsidian_vault_organize
version: 1.0.0
capability_code: obsidian_book
name: 整理 Obsidian Vault 為網站結構
description: |
  分析 Obsidian vault 的內容結構，設計網站架構，生成結構化專案目錄。這是網站生成流程的第一步：先分析內容結構並建立專案目錄（.mindscape/websites/{project_id}/），然後使用 obsidian_to_site_spec 從專案目錄生成網站規格（第二步）。適用於需要先分析內容結構、設計網站架構的場景。不適用於已有專案目錄或只需生成規格的情況（直接使用 obsidian_to_site_spec）。
tags:
  - obsidian
  - organization
  - website
  - structure
  - initial-setup
  - content-analysis

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
icon: 📁
---

# 整理 Obsidian Vault 為網站結構 - SOP

## 目標

分析 Obsidian vault 的內容結構，設計網站架構，並生成結構化的網站專案目錄到 `.mindscape/websites/{project_id}/`。

**工作流程說明**：
- 這是網站生成流程的**第一步**：先分析內容結構並建立專案目錄
- 完成後，可以使用 `obsidian_to_site_spec` 從專案目錄生成網站規格（第二步）

## 功能說明

這個 Playbook 會：

1. **掃描原始資料**：掃描 vault 根目錄或指定路徑的所有 Markdown 檔案
2. **LLM 分析**：讓 LLM 分析內容並設計適合網站的結構
3. **生成專案**：創建 `.mindscape/websites/{project_id}/` 專案目錄
4. **整理內容**：將原始內容整理並遷移到結構化目錄
5. **生成映射**：記錄原始檔案到結構化內容的映射關係

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.1: 檢查是否有活躍的 web_page project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page` 或 `website`
- 如果沒有，提示用戶需要先創建 project

#### 步驟 0.2: 獲取 Obsidian Vault 路徑
- 從 workspace settings 讀取 Obsidian vault 路徑
- 如果有多個 vault，詢問用戶選擇哪一個
- 如果沒有配置，提示用戶需要先配置

#### 步驟 0.3: 獲取專案參數
- 從用戶輸入獲取 `project_id`（可選，如果沒有則自動生成）
- 從用戶輸入獲取 `project_name`（可選，如果沒有則使用 project_id）
- 從用戶輸入獲取 `scan_root`（可選，預設 vault 根目錄）

### Phase 1: 掃描原始資料

#### 步驟 1.1: 掃描指定路徑
- 使用 `ObsidianBookReader.scan_flexible(root_path=scan_root)` 掃描所有 Markdown 檔案
- 收集檔案路徑、標題、內容摘要等信息

#### 步驟 1.2: 準備內容摘要
- 為每個檔案提取：
  - 檔案路徑
  - 標題（從 frontmatter 或檔案名稱）
  - 內容摘要（前 200 字）
  - 標籤（如果有）
- 生成內容摘要列表供 LLM 分析

### Phase 2: LLM 分析並設計結構

#### 步驟 2.1: 構建 LLM Prompt
- 將內容摘要列表格式化為 JSON
- 構建結構設計 Prompt：
  ```
  分析以下 Obsidian vault 的內容，設計一個適合網站的結構化目錄。

  內容列表：
  {content_summary}

  要求：
  1. 將相關內容分組到章節（建議 3-8 個章節）
  2. 設計清晰的層級結構（章節 → 小節）
  3. 考慮網站的導航和用戶體驗
  4. 保持內容的可維護性
  5. 使用有意義的 slug（小寫、連字符分隔）

  請以 JSON 格式返回結構設計和遷移計劃。
  ```

#### 步驟 2.2: 調用 LLM 生成結構設計
- 使用 LLM 分析內容並生成結構設計
- 解析 LLM 返回的 JSON：
  - `structure`: 章節結構定義
  - `migration_plan`: 原始檔案到新結構的映射
  - `rationale`: 設計理由

#### 步驟 2.3: 驗證結構設計
- 檢查結構設計的完整性
- 驗證所有原始檔案都有對應的遷移目標
- 如果驗證失敗，提示用戶或重新生成

### Phase 3: 創建專案目錄

#### 步驟 3.1: 初始化專案
- 使用 `WebsiteProjectManager.create_project()` 創建專案
- 生成 `.mindscape/websites/{project_id}/` 目錄
- 生成 `manifest.yaml` 專案配置

#### 步驟 3.2: 創建內容目錄結構
- 根據 LLM 設計的結構創建章節目錄
- 在 `content/chapters/` 下創建章節目錄
- 為每個章節創建 `00-intro.md` 介紹文件

### Phase 4: 遷移內容

#### 步驟 4.1: 遷移檔案
- 根據 `migration_plan` 遷移每個原始檔案
- 讀取原始檔案內容
- 添加或更新 frontmatter（包含 chapter, section, slug, title 等）
- 寫入到新的結構化位置

#### 步驟 4.2: 生成章節介紹
- 為每個章節生成 `00-intro.md` 介紹文件
- 包含章節標題、描述、小節列表

#### 步驟 4.3: 生成網站介紹
- 生成 `content/00-intro.md` 網站介紹文件
- 包含網站標題、描述、章節列表

#### 步驟 4.4: 保存映射關係
- 使用 `WebsiteProjectManager.save_mapping()` 保存映射關係
- 記錄原始檔案到結構化內容的對應關係
- 記錄同步時間和狀態

### Phase 5: 生成網站規格

#### 步驟 5.1: 掃描結構化內容
- 使用 `ObsidianBookReader.scan_flexible(root_path=content_dir)` 掃描結構化內容
- 構建頁面樹結構

#### 步驟 5.2: 生成 site_structure.yaml
- 根據頁面樹生成網站規格
- 保存到專案目錄的 `site_structure.yaml`
- 同時保存到 Project Sandbox 的 `spec/site_structure.yaml`

#### 步驟 5.3: 更新專案配置
- 更新 `manifest.yaml` 的 `generation` 欄位
- 記錄生成時間和生成器信息

### Phase 6: 驗證和摘要

#### 步驟 6.1: 驗證生成結果
- 檢查所有檔案是否正確生成
- 檢查 frontmatter 是否完整
- 檢查映射關係是否正確

#### 步驟 6.2: 生成執行摘要
- 列出創建的專案信息
- 列出整理的章節和頁面數量
- 列出原始檔案到新結構的映射
- 提供後續步驟建議

## 輸入參數

- `project_id`（可選）：專案 ID（如果沒有，自動生成，格式：`{project_name}-{timestamp}`）
- `project_name`（可選）：專案名稱（如果沒有，使用 project_id）
- `scan_root`（可選）：掃描根路徑（預設 vault 根目錄）
- `vault_path`（可選）：Obsidian vault 路徑（如果沒有在 settings 中配置）

**使用範例**：
- 基本使用：`project_name=Mindscape Book 2025`
- 指定掃描路徑：`project_name=Mindscape Book 2025, scan_root=mindscape-book`
- 指定專案 ID：`project_id=mindscape-book-2025, project_name=Mindscape Book 2025`

## 輸出

- 專案目錄：`.mindscape/websites/{project_id}/`
- 專案配置：`manifest.yaml`
- 結構化內容：`content/` 目錄
- 來源映射：`sources/mapping.yaml`
- 網站規格：`site_structure.yaml`（專案目錄和 Project Sandbox）

## 成功標準

- ✅ 成功創建專案目錄和配置
- ✅ 成功整理所有原始內容到結構化目錄
- ✅ 成功生成來源映射關係
- ✅ 成功生成網站規格文件
- ✅ 所有檔案包含完整的 frontmatter

## 注意事項

- **原始資料保留**：原始檔案不會被刪除或移動，只是複製到新結構
- **專案隔離**：每個專案有獨立的目錄，不會互相影響
- **長期維護**：生成的結構化內容可以長期維護和更新
- **內容同步**：可以使用 `obsidian_content_sync` playbook 同步原始資料的更新

## 相關文檔

- **網站內容管理架構**：`docs-internal/implementation/website-content-management-architecture.md`
- **WebsiteProjectManager**：`tools/website_project_manager.py`
- **ObsidianBookReader**：`tools/obsidian_book_reader.py`

