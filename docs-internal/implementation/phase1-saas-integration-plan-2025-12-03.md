# 第一階段第三方 SaaS 整合實作計劃

**日期**：2025-12-03
**階段**：第一階段 - 高優先級服務整合
**狀態**：規劃中

---

## 📋 實作目標

實作以下四個高優先級第三方 SaaS 服務整合：

1. **Slack** - 協作通訊整合
2. **Airtable** - 結構化資料管理
3. **Google Sheets** - 試算表整合
4. **GitHub** - 程式碼管理整合

---

## 🏗️ 架構設計

### 實作模式

遵循現有架構模式，每個服務包含以下組件：

#### Backend 組件

1. **Provider Routes** (`backend/app/routes/core/tools/providers/xxx.py`)
   - `/api/v1/tools/xxx/discover` - 發現工具能力
   - `/api/v1/tools/xxx/connect` - 建立連接
   - `/api/v1/tools/xxx/validate` - 驗證連接（可選）
   - OAuth 相關端點（如需要）

2. **Discovery Provider** (`backend/app/services/tools/providers/xxx_provider.py`)
   - 實作 `ToolDiscoveryProvider` 介面
   - 定義可發現的工具能力
   - 驗證配置

3. **Tools Implementation** (`backend/app/services/tools/xxx/xxx_tools.py`)
   - 實作具體的工具類別（繼承 `MindscapeTool`）
   - 實作工具執行邏輯

4. **OAuth Manager** (`backend/app/services/tools/xxx/oauth_manager.py`) - 如需要
   - OAuth 2.0 流程管理
   - Token 儲存與刷新

#### Frontend 組件

1. **Connection Wizard** (`web-console/src/app/settings/components/wizards/xxxConnectionWizard.tsx`)
   - 連接配置表單
   - OAuth 流程處理（如需要）
   - 錯誤處理與成功提示

2. **Tools Panel 註冊** (`web-console/src/app/settings/components/ToolsPanel.tsx`)
   - 將新服務加入 `EXTERNAL_SAAS_TOOLS` 列表

3. **i18n 支援** (`web-console/src/lib/i18n/locales/`)
   - 新增服務相關翻譯字串

---

## 📝 實作清單

### 1. Slack 整合

#### API 資訊
- **API 文檔**：https://api.slack.com/
- **認證方式**：OAuth 2.0
- **Base URL**：https://slack.com/api/

#### 實作功能
- [ ] Provider Routes (`slack.py`)
  - [ ] `/api/v1/tools/slack/discover`
  - [ ] `/api/v1/tools/slack/connect`
  - [ ] `/api/v1/tools/slack/oauth/authorize`
  - [ ] `/api/v1/tools/slack/oauth/callback`
  - [ ] `/api/v1/tools/slack/validate`

- [ ] Discovery Provider (`slack_provider.py`)
  - [ ] 發現工具：`slack_send_message`, `slack_read_channel`, `slack_list_channels`, `slack_upload_file`

- [ ] Tools Implementation (`slack/slack_tools.py`)
  - [ ] `SlackSendMessageTool` - 發送訊息到頻道
  - [ ] `SlackReadChannelTool` - 讀取頻道訊息
  - [ ] `SlackListChannelsTool` - 列出工作空間頻道
  - [ ] `SlackUploadFileTool` - 上傳檔案到頻道

- [ ] OAuth Manager (`slack/oauth_manager.py`)
  - [ ] OAuth 2.0 授權流程
  - [ ] Token 儲存與刷新

- [ ] Frontend Wizard (`SlackConnectionWizard.tsx`)
  - [ ] OAuth 連接表單
  - [ ] 連接狀態顯示

- [ ] i18n 支援
  - [ ] 新增 Slack 相關翻譯

#### 預估時間：4-6 小時

---

### 2. Airtable 整合

#### API 資訊
- **API 文檔**：https://airtable.com/api
- **認證方式**：OAuth 2.0 / Personal Access Token
- **Base URL**：https://api.airtable.com/v0/

#### 實作功能
- [ ] Provider Routes (`airtable.py`)
  - [ ] `/api/v1/tools/airtable/discover`
  - [ ] `/api/v1/tools/airtable/connect`
  - [ ] `/api/v1/tools/airtable/validate`

- [ ] Discovery Provider (`airtable_provider.py`)
  - [ ] 發現工具：`airtable_list_bases`, `airtable_read_table`, `airtable_create_record`, `airtable_update_record`, `airtable_delete_record`

- [ ] Tools Implementation (`airtable/airtable_tools.py`)
  - [ ] `AirtableListBasesTool` - 列出所有 Bases
  - [ ] `AirtableReadTableTool` - 讀取表格資料
  - [ ] `AirtableCreateRecordTool` - 建立記錄
  - [ ] `AirtableUpdateRecordTool` - 更新記錄
  - [ ] `AirtableDeleteRecordTool` - 刪除記錄

- [ ] Frontend Wizard (`AirtableConnectionWizard.tsx`)
  - [ ] API Key 或 OAuth 選擇
  - [ ] 連接配置表單

- [ ] i18n 支援
  - [ ] 新增 Airtable 相關翻譯

#### 預估時間：3-4 小時

---

### 3. Google Sheets 整合

#### API 資訊
- **API 文檔**：https://developers.google.com/sheets/api
- **認證方式**：OAuth 2.0 (Google API) - 可共用 Google Drive 的 OAuth
- **Base URL**：https://sheets.googleapis.com/v4/

#### 實作功能
- [ ] Provider Routes (`google_sheets.py`)
  - [ ] `/api/v1/tools/google_sheets/discover`
  - [ ] `/api/v1/tools/google_sheets/connect`
  - [ ] `/api/v1/tools/google_sheets/validate`
  - [ ] 共用 Google Drive OAuth（如已配置）

- [ ] Discovery Provider (`google_sheets_provider.py`)
  - [ ] 發現工具：`google_sheets_read_range`, `google_sheets_write_range`, `google_sheets_append_rows`, `google_sheets_list_spreadsheets`

- [ ] Tools Implementation (`google_sheets/google_sheets_tools.py`)
  - [ ] `GoogleSheetsReadRangeTool` - 讀取範圍資料
  - [ ] `GoogleSheetsWriteRangeTool` - 寫入範圍資料
  - [ ] `GoogleSheetsAppendRowsTool` - 追加列
  - [ ] `GoogleSheetsListSpreadsheetsTool` - 列出試算表

- [ ] OAuth 整合
  - [ ] 檢查是否已有 Google OAuth 配置
  - [ ] 共用或建立新的 OAuth 連接

- [ ] Frontend Wizard (`GoogleSheetsConnectionWizard.tsx`)
  - [ ] OAuth 連接（可共用 Google Drive）
  - [ ] 試算表選擇

- [ ] i18n 支援
  - [ ] 新增 Google Sheets 相關翻譯

#### 預估時間：3-4 小時（可重用 Google Drive OAuth）

---

### 4. GitHub 整合

#### API 資訊
- **API 文檔**：https://docs.github.com/en/rest
- **認證方式**：OAuth 2.0 / Personal Access Token
- **Base URL**：https://api.github.com/

#### 實作功能
- [ ] Provider Routes (`github.py`)
  - [ ] `/api/v1/tools/github/discover`
  - [ ] `/api/v1/tools/github/connect`
  - [ ] `/api/v1/tools/github/oauth/authorize`
  - [ ] `/api/v1/tools/github/oauth/callback`
  - [ ] `/api/v1/tools/github/validate`

- [ ] Discovery Provider (`github_provider.py`)
  - [ ] 發現工具：`github_list_repos`, `github_read_file`, `github_create_issue`, `github_list_issues`, `github_create_pr`, `github_search_code`

- [ ] Tools Implementation (`github/github_tools.py`)
  - [ ] `GitHubListReposTool` - 列出 Repository
  - [ ] `GitHubReadFileTool` - 讀取檔案內容
  - [ ] `GitHubCreateIssueTool` - 建立 Issue
  - [ ] `GitHubListIssuesTool` - 列出 Issues
  - [ ] `GitHubCreatePRTool` - 建立 Pull Request
  - [ ] `GitHubSearchCodeTool` - 搜尋程式碼

- [ ] OAuth Manager (`github/oauth_manager.py`)
  - [ ] OAuth 2.0 授權流程
  - [ ] Token 儲存

- [ ] Frontend Wizard (`GitHubConnectionWizard.tsx`)
  - [ ] OAuth 或 Personal Access Token 選擇
  - [ ] 連接配置表單

- [ ] i18n 支援
  - [ ] 新增 GitHub 相關翻譯

#### 預估時間：4-5 小時

---

## 🔧 實作步驟

### 步驟 1：環境準備
- [ ] 確認開發環境正常運行
- [ ] 準備測試用的 API 憑證（不提交到 Git）

### 步驟 2：實作順序
1. **Slack** - 最複雜，先實作建立完整模式
2. **Airtable** - 相對簡單，驗證模式
3. **Google Sheets** - 可重用 OAuth，驗證共用機制
4. **GitHub** - 功能豐富，完善模式

### 步驟 3：每個服務的實作流程
1. 建立 Backend Provider Routes
2. 實作 Discovery Provider
3. 實作 Tools
4. 實作 OAuth Manager（如需要）
5. 建立 Frontend Wizard
6. 註冊到 Tools Panel
7. 新增 i18n 翻譯
8. 測試連接與功能

### 步驟 4：測試與驗證
- [ ] 單元測試
- [ ] 整合測試
- [ ] 手動測試連接流程
- [ ] 驗證工具執行

### 步驟 5：文件更新
- [ ] 更新開發者指南（如需要）
- [ ] 更新 API 文檔
- [ ] 更新使用者指南

---

## ⚠️ 注意事項

### 開發規範

1. **本地優先原則**
   - 所有整合必須透過 adapter 模式
   - 核心功能必須能在本地完全運行
   - 雲端服務為可選擴展

2. **安全規範**
   - 嚴禁硬編碼 API Key 或敏感資訊
   - 必須使用環境變數管理認證資訊
   - 遵循 OAuth 2.0 最佳實踐

3. **程式碼規範**
   - 程式碼註釋使用英文（i18n 基底）
   - 內部文檔使用繁體中文
   - 禁用實作步驟與紀錄、非功能性描述、emoji

4. **Git 工作流程**
   - 絕不允許繞過 Git 直接修改 VM
   - 所有變更必須透過 Git 提交
   - 提交前必須查驗註釋

### 技術考量

1. **OAuth 流程**
   - 實作標準 OAuth 2.0 流程
   - 妥善處理 Token 刷新
   - 錯誤處理與重試機制

2. **錯誤處理**
   - 統一的錯誤回應格式
   - 清晰的錯誤訊息
   - 適當的日誌記錄

3. **測試策略**
   - Mock API 回應進行單元測試
   - 整合測試使用測試帳號
   - 避免在測試中使用真實生產憑證

---

## 📊 進度追蹤

### 整體進度
- [ ] Slack 整合（0%）
- [ ] Airtable 整合（0%）
- [ ] Google Sheets 整合（0%）
- [ ] GitHub 整合（0%）

### 預計完成時間
- **開始日期**：2025-12-03
- **預計完成**：2025-12-10（7 天）
- **總預估時間**：14-19 小時

---

## 📚 參考資源

### API 文檔
- [Slack API](https://api.slack.com/)
- [Airtable API](https://airtable.com/api)
- [Google Sheets API](https://developers.google.com/sheets/api)
- [GitHub API](https://docs.github.com/en/rest)

### 現有實作參考
- `backend/app/routes/core/tools/providers/notion.py`
- `backend/app/services/tools/providers/notion_provider.py`
- `backend/app/services/tools/notion/notion_tools.py`
- `web-console/src/app/settings/components/wizards/NotionConnectionWizard.tsx`

### 相關文檔
- [開發者指南](../DEVELOPER_GUIDE_MINDSCAPE_AI.md)
- [第三方 SaaS 整合調查報告](./third-party-saas-integration-survey-2025-12-03.md)

---

**最後更新**：2025-12-03
**維護者**：Mindscape AI 開發團隊
**狀態**：規劃完成，準備開始實作

