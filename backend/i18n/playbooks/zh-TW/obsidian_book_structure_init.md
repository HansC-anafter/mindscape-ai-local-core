---
playbook_code: obsidian_book_structure_init
version: 1.0.0
capability_code: obsidian_book
name: 初始化 Obsidian 書籍結構
description: 為指定年份初始化 Obsidian vault 中的書籍結構，創建必要的文件夾和模板文件
tags:
  - obsidian
  - book
  - structure
  - initialization

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
icon: 📚
---

# 初始化 Obsidian 書籍結構 - SOP

## 目標

為指定年份初始化 Obsidian vault 中的書籍結構，創建必要的文件夾和模板文件（帶 frontmatter）。

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.1: 檢查是否有活躍的 book project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `book` 或 `obsidian_book`
- 如果沒有，提示用戶需要先創建 book project

#### 步驟 0.2: 獲取 Obsidian Vault 路徑
- 從 workspace settings 讀取 Obsidian vault 路徑：
  ```python
  workspace = await store.get_workspace(workspace_id)
  vault_paths = workspace.settings.get("obsidian", {}).get("vault_paths", [])
  ```
- 如果有多個 vault，詢問用戶選擇哪一個
- 如果沒有配置 vault 路徑，提示用戶需要先配置

#### 步驟 0.3: 獲取年份和書籍信息
- 從用戶輸入或 project context 獲取年份
- 如果沒有提供，使用當前年份
- 獲取書籍標題和 slug（如果沒有，使用默認值）

### Phase 1: 驗證和準備

#### 步驟 1.1: 驗證 Vault 路徑
- 確認 vault 路徑存在且可寫
- 檢查 `books/` 目錄是否存在，如果不存在則創建

#### 步驟 1.2: 檢查是否已存在書籍結構
- 檢查 `books/{year}/` 目錄是否已存在
- 如果存在，詢問用戶是否要覆蓋或更新
- 如果不存在，繼續初始化

#### 步驟 1.3: 生成書籍標識
- 生成書籍標識：`{year}-{book-slug}`
- 如果沒有提供 slug，使用默認值（如 "mindscape"）

### Phase 2: 創建目錄結構

#### 步驟 2.1: 創建書籍根目錄
- 創建 `books/{year}/` 目錄
- 創建 `books/{year}/chapters/` 目錄
- 創建 `books/{year}/assets/` 目錄
- 創建 `books/{year}/assets/images/` 目錄
- 創建 `books/{year}/assets/attachments/` 目錄

#### 步驟 2.2: 驗證目錄創建
- 確認所有目錄都已成功創建
- 如果創建失敗，記錄錯誤並提示用戶

### Phase 3: 生成模板文件

#### 步驟 3.1: 生成 `00-intro.md`（書籍介紹）

**文件路徑**：`books/{year}/00-intro.md`

**Frontmatter**：
```yaml
---
book: "{year}-{book-slug}"
type: "intro"
year: {year}
title: "{書籍標題}"
description: "{書籍描述}"
status: "draft"
tags: ["book", "{book-slug}"]
created_at: "{當前日期}"
updated_at: "{當前日期}"
---
```

**內容模板**：
```markdown
# {書籍標題}

{書籍描述}

## 目錄

（章節列表將在後續添加）

## 關於這本書

（關於書籍的說明）
```

#### 步驟 3.2: 生成 `01-chapter-structure.md`（章節結構規劃）

**文件路徑**：`books/{year}/01-chapter-structure.md`

**Frontmatter**：
```yaml
---
book: "{year}-{book-slug}"
type: "structure"
year: {year}
status: "draft"
tags: ["book", "structure"]
created_at: "{當前日期}"
updated_at: "{當前日期}"
---
```

**內容模板**：
```markdown
# 章節結構規劃

## 章節列表

（章節結構將在後續規劃）

## 章節規劃說明

（章節規劃的說明）
```

### Phase 4: 保存文件

#### 步驟 4.1: 保存書籍介紹文件
- 使用 `filesystem_write_file` 工具保存 `00-intro.md`
- 確保 frontmatter 格式正確
- 確保內容格式正確

#### 步驟 4.2: 保存章節結構文件
- 使用 `filesystem_write_file` 工具保存 `01-chapter-structure.md`
- 確保 frontmatter 格式正確
- 確保內容格式正確

#### 步驟 4.3: 驗證文件創建
- 確認所有文件都已成功創建
- 驗證 frontmatter 格式
- 如果創建失敗，記錄錯誤並提示用戶

### Phase 5: 生成摘要和後續步驟

#### 步驟 5.1: 生成初始化摘要
- 列出已創建的目錄結構
- 列出已創建的文件
- 提供書籍標識和路徑信息

#### 步驟 5.2: 提供後續步驟建議
- 建議下一步：使用 `yearly_personal_book` playbook 生成內容
- 建議下一步：手動創建章節結構
- 提供相關 playbook 的使用說明

## 輸入參數

- `year`（可選）：年份，默認為當前年份
- `book_title`（可選）：書籍標題
- `book_slug`（可選）：書籍 slug，默認為 "mindscape"
- `book_description`（可選）：書籍描述
- `vault_path`（可選）：Obsidian vault 路徑（如果沒有在 settings 中配置）

## 輸出

- 書籍根目錄：`books/{year}/`
- 書籍介紹文件：`books/{year}/00-intro.md`
- 章節結構文件：`books/{year}/01-chapter-structure.md`
- 目錄結構：`chapters/`, `assets/` 等

## 預期結果

- ✅ Obsidian vault 中已創建完整的書籍目錄結構
- ✅ 已生成帶 frontmatter 的模板文件
- ✅ 所有文件符合 Obsidian Book Structure Convention
- ✅ 用戶可以開始使用書籍結構進行寫作

## 注意事項

- 如果書籍結構已存在，會詢問用戶是否覆蓋
- 需要確保 Obsidian vault 路徑已正確配置
- Frontmatter 必須符合規範（參考 `frontmatter-schema.yaml`）
- 文件路徑使用正斜杠 `/`，符合 Obsidian 的內部路徑格式

## 相關文檔

- **結構規範**：`docs/obsidian-book-structure-convention.md`
- **Frontmatter Schema**：`docs/frontmatter-schema.yaml`

