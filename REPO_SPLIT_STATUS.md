# Repo 分家狀態

**建立日期**: 2025-12-02
**狀態**: 初始結構已建立
**目的**: 記錄 core + local 分家進度

---

## ✅ 已完成

### 核心檔案

- [x] `backend/app/core/execution_context.py` - ExecutionContext 定義
- [x] `backend/app/core/ports/` - Port 介面（IdentityPort, IntentRegistryPort）
- [x] `backend/app/adapters/local/` - Local Adapters
- [x] `backend/app/services/conversation/` - 核心服務（部分）

### 文檔

- [x] `README.md` - 開源版 README
- [x] `LICENSE` - MIT License
- [x] `CONTRIBUTING.md` - 貢獻指南
- [x] `QUICKSTART.md` - 快速開始
- [x] `docs/architecture/` - 架構文檔

### Git 初始化

- [x] Git 倉庫初始化
- [x] 初始 commit
- [x] `.gitignore` 設定

---

## 📋 待完成

### 需要複製的檔案

#### Services 層（需要檢查依賴）

- [ ] `backend/app/services/intent_llm_extractor.py`
- [ ] `backend/app/services/playbook_loader.py`
- [ ] `backend/app/services/playbook_runner.py`
- [ ] `backend/app/services/mindscape_store.py`
- [ ] `backend/app/services/i18n_service.py`
- [ ] 其他依賴的服務

#### Models 層

- [ ] `backend/app/models/workspace.py`
- [ ] `backend/app/models/mindscape.py`
- [ ] `backend/app/models/export.py`
- [ ] 其他必要的 models

#### Stores 層

- [ ] `backend/app/services/stores/workspaces_store.py`
- [ ] `backend/app/services/stores/tasks_store.py`
- [ ] `backend/app/services/stores/timeline_items_store.py`
- [ ] `backend/app/services/stores/artifacts_store.py`
- [ ] `backend/app/services/stores/intent_tags_store.py`

#### Routes 層

- [ ] `backend/app/routes/workspace_chat.py`
- [ ] `backend/app/routes/workspace_executions.py`
- [ ] `backend/app/routes/workspace_timeline.py`
- [ ] 其他必要的 routes

#### 其他必要檔案

- [ ] `backend/app/main.py`
- [ ] `backend/app/__init__.py`
- [ ] `backend/requirements.txt`
- [ ] `backend/requirements-tools.txt`
- [ ] `backend/pyproject.toml`（如果有）

#### 前端（可選，或後續添加）

- [ ] `web-console/` - 整個前端目錄

---

## ❌ 必須排除的檔案

### Cloud Clients

- [ ] `backend/app/services/clients/site_hub_client.py` - 不包含
- [ ] `backend/app/services/clients/semantic_hub_client.py` - 不包含

### Cloud Extensions

- [ ] `backend/app/extensions/multi_cluster_bridge/` - 不包含

### Cloud 文檔

- [ ] `docs/console-kit/` - 已移除

---

## 🔍 需要檢查的事項

### 依賴檢查

- [ ] 確認所有服務不直接依賴 `site_hub_client` 或 `semantic_hub_client`
- [ ] 確認所有 cloud 相關邏輯都在 adapter 層（開源版沒有 cloud adapter）

### 代碼檢查

- [ ] 搜尋所有檔案，確認沒有硬編 `tenant_id`、`group_id`
- [ ] 確認沒有直接 import cloud clients
- [ ] 確認所有 cloud 相關邏輯都在 adapter 層

---

## 📝 下一步

1. **複製必要的服務和模型**
   - 檢查依賴關係
   - 複製必要的檔案
   - 確認沒有 cloud 依賴

2. **複製必要的 routes**
   - 檢查是否有 cloud 相關路由
   - 複製必要的 routes

3. **複製必要的 stores**
   - 檢查是否有 cloud 相關 store
   - 複製必要的 stores

4. **複製前端（可選）**
   - 檢查是否有 cloud 相關 UI
   - 複製前端檔案

5. **測試**
   - 確認所有依賴都滿足
   - 確認可以正常運行

---

**最後更新**: 2025-12-02
**狀態**: 初始結構已建立，待複製完整檔案

