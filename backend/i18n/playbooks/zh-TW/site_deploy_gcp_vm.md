---
playbook_code: site_deploy_gcp_vm
version: 1.0.0
capability_code: web_generation
name: 網站部署到 GCP VM
description: 將生成的網站組件透過 Git 工作流程部署到 GCP VM 生產環境
tags:
  - deployment
  - gcp
  - vm
  - git
  - production

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - filesystem_read_file
  - filesystem_write_file

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 🚀
---

# 網站部署到 GCP VM - SOP

## 目標
將生成的完整網站組件透過 Git 工作流程部署到 GCP VM 生產環境。**嚴格遵守開發者規範：絕不允許繞過 Git 直接操作 VM。**

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.1: 檢查是否有活躍的 web_page project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page` 或 `website`
- 如果沒有，提示用戶需要先創建 project

#### 步驟 0.2: 獲取 Project Sandbox 路徑
- 使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/{project_type}/{project_id}/`
- 確認已生成的組件存在

#### 步驟 0.3: 檢查依賴的 Artifacts
檢查以下 artifacts 是否存在：
- `complete_page` - 完整網頁組件（`pages/index.tsx`）
- `hero_component` - Hero 組件（`hero/Hero.tsx`）
- `sections` - Sections 組件（`sections/` 目錄）

如果任何一個不存在，提示用戶需要先執行對應的 playbook。

### Phase 1: 準備部署檔案

#### 步驟 1.1: 讀取生成的組件
**必須**使用 `filesystem_read_file` 工具讀取：

- **完整網頁組件**：`pages/index.tsx`
- **Hero 組件**：`hero/Hero.tsx`
- **所有 Section 組件**：`sections/*.tsx`
- **樣式檔案**（如有）：`styles/*.css` 或 `styles/*.ts`
- **依賴清單**：`package.json` 或 `dependencies.md`

#### 步驟 1.2: 驗證組件完整性
- 檢查所有組件是否有 TypeScript 錯誤
- 檢查所有導入路徑是否正確
- 檢查依賴是否完整
- 驗證組件結構符合目標專案規範

#### 步驟 1.3: 準備 Git 提交內容
- 確定目標 Git 倉庫路徑（site-brand 或其他專案）
- 規劃檔案結構和放置位置
- 準備提交訊息（符合 Conventional Commits 規範）

### Phase 2: Git 工作流程

#### 步驟 2.1: 檢查 Git 倉庫狀態
- 確認目標 Git 倉庫路徑存在
- 檢查當前分支（應在功能分支，不在 main/master）
- 確認工作目錄乾淨（無未提交變更）

#### 步驟 2.2: 創建功能分支（如需要）
如果當前不在功能分支：
- 創建新的功能分支：`feature/deploy-{project_id}-{timestamp}`
- 分支命名規範：`feature/deploy-{description}`

#### 步驟 2.3: 複製檔案到目標位置
**必須**使用 `filesystem_write_file` 工具將組件寫入目標位置：

- **組件檔案**：寫入到目標專案的組件目錄
  - 例如：`site-brand/sites/{site-name}/src/components/Home/Hero.tsx`
- **頁面檔案**：更新或創建頁面檔案
  - 例如：`site-brand/sites/{site-name}/src/pages/index.tsx`
- **樣式檔案**：寫入樣式目錄（如有）
- **配置檔案**：更新 `package.json` 等配置（如有需要）

#### 步驟 2.4: 生成 Git 提交指令
**必須**生成 Git 提交指令，但**不直接執行**（由用戶確認後執行）：

```bash
# 檢查變更
git status

# 添加檔案（明確指定檔案，嚴禁 git add .）
git add [明確的檔案名稱]

# 提交變更（符合 Conventional Commits 規範）
git commit -m "feat(site): deploy {project_name} to production

- Add hero component: Hero.tsx
- Add page sections: About.tsx, Features.tsx, etc.
- Update main page: index.tsx
- Generated via playbook: site_deploy_gcp_vm"

# 推送到遠端
git push origin feature/deploy-{project_id}-{timestamp}
```

**重要**：
- 必須明確指定檔案名稱，嚴禁使用 `git add .`
- 提交訊息必須符合 Conventional Commits 規範
- 必須在功能分支提交，不在 main/master 直接提交

### Phase 3: 部署準備

#### 步驟 3.1: 生成部署檢查清單
生成部署前檢查清單：

- [ ] 所有組件檔案已正確寫入
- [ ] TypeScript 編譯無錯誤
- [ ] 所有依賴已安裝
- [ ] Git 變更已提交到功能分支
- [ ] Pull Request 已創建（如需要）
- [ ] 代碼審查已通過（如需要）

#### 步驟 3.2: 生成部署指令
生成部署到 GCP VM 的指令（**不直接執行**，由用戶確認後執行）：

```bash
# 方式 1: 透過 Git 部署（推薦）
# 在 GCP VM 上執行
cd /path/to/site-brand
git pull origin main  # 或 develop，取決於部署流程
npm install  # 如有新依賴
npm run build  # 構建專案
pm2 restart site-brand  # 或使用其他進程管理器

# 方式 2: 透過 CI/CD 部署（如已配置）
# 推送後自動觸發部署流程
```

#### 步驟 3.3: 生成部署驗證步驟
生成部署後驗證步驟：

- 檢查網站是否正常運行
- 檢查 Three.js 場景是否正常載入
- 檢查 GSAP 動畫是否流暢運行
- 檢查響應式設計在行動裝置上的表現
- 檢查效能（目標 60fps）
- 檢查控制台是否有錯誤

### Phase 4: 文件生成與保存

#### 步驟 4.1: 保存部署計劃
**必須**使用 `filesystem_write_file` 工具保存部署計劃：

- **文件路徑**：`artifacts/site_deploy_gcp_vm/{{execution_id}}/deployment_plan.md`
- **內容**：
  - 部署目標（GCP VM 資訊）
  - Git 倉庫路徑
  - 檔案放置位置
  - Git 提交指令
  - 部署指令
  - 驗證步驟
- **格式**：Markdown 格式

#### 步驟 4.2: 保存 Git 變更摘要
**必須**使用 `filesystem_write_file` 工具保存 Git 變更摘要：

- **文件路徑**：`artifacts/site_deploy_gcp_vm/{{execution_id}}/git_changes.md`
- **內容**：
  - 變更的檔案列表
  - 每個檔案的變更摘要
  - Git 提交訊息
  - 分支名稱

#### 步驟 4.3: 保存對話歷史
**必須**使用 `filesystem_write_file` 工具保存完整的對話歷史：

- **文件路徑**：`artifacts/site_deploy_gcp_vm/{{execution_id}}/conversation_history.json`
- **內容**：完整的對話歷史（包含所有 user 和 assistant 消息）
- **格式**：JSON 格式，包含時間戳和角色信息

#### 步驟 4.4: 保存執行摘要
**必須**使用 `filesystem_write_file` 工具保存執行摘要：

- **文件路徑**：`artifacts/site_deploy_gcp_vm/{{execution_id}}/execution_summary.md`
- **內容**：
  - 執行時間
  - 執行 ID
  - Playbook 名稱
  - 部署目標
  - 生成的檔案列表
  - Git 提交指令
  - 部署指令
  - 執行結果摘要

### Phase 5: 用戶確認與後續步驟

#### 步驟 5.1: 提供部署摘要
向用戶提供完整的部署摘要：

- 生成的檔案位置
- Git 提交指令（需要用戶確認後執行）
- 部署指令（需要用戶確認後執行）
- 部署檢查清單
- 驗證步驟

#### 步驟 5.2: 等待用戶確認
**重要**：所有 Git 操作和部署操作都必須等待用戶確認後才執行。

- 提供清晰的指令和說明
- 等待用戶確認後再進行下一步
- 如果用戶需要修改，提供修改指引

#### 步驟 5.3: 提供後續支援
提供後續支援資訊：

- 如何回滾部署（如需要）
- 如何查看部署日誌
- 如何監控網站狀態
- 如何進行後續更新

## 個人化

基於使用者的 Mindscape 個人檔案：
- **技術等級**：若為「進階」，提供更詳細的部署選項和自訂配置
- **詳細程度**：若偏好「高」，提供更詳細的部署步驟和驗證清單
- **工作風格**：若偏好「結構化」，提供更清晰的部署流程和檢查點

## 與長期意圖的整合

若使用者有相關的活躍意圖（例如「建立公司登陸頁面」），明確引用：
> "由於您正在進行「建立公司登陸頁面」，我已經準備好將生成的網站部署到生產環境..."

## 成功標準

- 所有組件檔案已正確寫入目標位置
- Git 提交指令已生成（符合規範）
- 部署指令已生成
- 部署計劃文件已保存
- 用戶已確認部署步驟
- 所有變更都透過 Git 工作流程進行（無直接操作 VM）

## 注意事項

### ⚠️ 絕對死線規範

1. **💀 絕不允許繞過 Git 直接操作 VM**
   - 所有變更必須透過 Git 提交
   - 所有部署必須透過 Git 工作流程
   - 嚴禁直接 SSH 到 VM 修改檔案

2. **💀 嚴禁使用 `git add .`**
   - 必須明確指定檔案名稱
   - 必須清楚知道每個變更的內容

3. **💀 嚴禁在 main/master 分支直接提交**
   - 必須在功能分支提交
   - 必須透過 Pull Request 合併（如需要）

4. **💀 提交訊息必須符合規範**
   - 使用 Conventional Commits 格式
   - 提供清晰的變更說明

### 其他注意事項

- **依賴關係**：必須先執行 `page_outline`、`threejs_hero_landing`、`page_sections`、`page_assembly` playbook
- **Project Context**：必須在 web_page project 的 context 中執行
- **Git 倉庫**：必須確認目標 Git 倉庫路徑正確
- **部署確認**：所有部署操作必須等待用戶確認
- **版本控制**：保留部署歷史以便回滾
- **執行記錄**：必須保存完整的對話歷史和執行摘要

## 相關文檔

- **開發者規範**：`docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md`
- **Git 工作流程**：開發者文檔中的 Git 工作流程章節
- **部署架構**：`docs-internal/core-architecture/cloud-local-deployment-guide.md`

