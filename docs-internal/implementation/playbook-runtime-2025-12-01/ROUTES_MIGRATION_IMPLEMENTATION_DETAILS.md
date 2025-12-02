# Routes 遷移實作細項

**建立日期**：2025-12-02
**最後更新**：2025-12-02
**狀態**：Phase 1-3 路由遷移完成，Phase 2 adapter 實作待完成
**負責人**：開發團隊

本文檔記錄 Routes 遷移實作的詳細步驟、檢查清單與驗證標準。

## ⚠️ 未完成項目清單

### Phase 2 - 後續階段（待實作）

#### 2.1.1 Vector DB Adapter 實作
- [ ] **實作 `VectorStorePort` 介面**（如尚未存在）
- [ ] **實作 adapter 模式**
- [ ] **接上具體的向量資料庫**（Postgres+pgvector / Weaviate / local-FAISS）
- [ ] **更新 `_check_vector_store_adapter()` 檢查邏輯**
- [ ] **實作實際的配置和連接功能**
- [ ] **有 adapter 時可以正常運作**

#### 2.2.1 Vector Search Adapter 實作
- [ ] **實作 adapter 模式**
- [ ] **接上具體的向量資料庫**
- [ ] **實作實際的向量搜尋功能**
- [ ] **有 adapter 時可以正常運作**

**注意**：Phase 2 的 `vector_db.py` 和 `vector_search.py` 目前是 **stub 實現**（返回 501），這是計劃中的第一階段。完整的 adapter 實作是後續階段。

### Phase 2 - 路由前綴問題
- [ ] **修復 `vector_search.py` 路由前綴**：目前是 `/api/vector`，應該改為 `/api/v1/vector` 以統一 API 版本

---

## 📋 實作前準備

### 環境檢查

- [ ] 確認已閱讀 `DEVELOPER_GUIDE_MINDSCAPE_AI.md`
- [ ] 確認已理解三層架構原則（Layer 0/1/2）
- [ ] 確認已理解 Port/Adapter 架構模式
- [ ] 確認開發環境已啟動（`docker compose ps`）

### 來源與目標確認

- [ ] 確認舊 repo 路徑：`my-agent-mindscape/backend/app/routes/`
- [ ] 確認新 repo 路徑：`mindscape-ai-local-core/backend/app/routes/`
- [ ] 確認目標目錄結構已建立

---

## Phase 1: Layer 0 - Kernel Routes（必須寫死）

### 1.1 複製 `workspace.py`

**來源**：`my-agent-mindscape/backend/app/routes/workspace.py`
**目標**：`mindscape-ai-local-core/backend/app/routes/core/workspace.py`

**實作步驟**：
1. [ ] 讀取來源檔案
2. [ ] 檢查並移除所有 cloud/tenant 相關內容
3. [ ] 檢查並移除硬編碼的 API keys
4. [ ] 確認所有環境變數從 `.env` 讀取
5. [ ] 複製到目標位置
6. [ ] 更新 import 路徑（如有需要）
7. [ ] 確認程式碼註釋為英文
8. [ ] 執行基本語法檢查

**檢查清單**：
- [ ] 無 `cloud`、`tenant`、`multi-tenant` 等關鍵字
- [ ] 無硬編碼的 API keys
- [ ] 無硬編碼的資料庫連線字串
- [ ] 所有配置從環境變數讀取
- [ ] 符合本地優先原則
- [ ] 程式碼註釋為英文

**驗證標準**：
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範

---

### 1.2 複製 `playbook.py`

**來源**：`my-agent-mindscape/backend/app/routes/playbook.py`
**目標**：`mindscape-ai-local-core/backend/app/routes/core/playbook.py`

**實作步驟**：
1. [ ] 讀取來源檔案
2. [ ] 檢查並移除所有 cloud/tenant 相關內容
3. [ ] 檢查並移除硬編碼的 API keys
4. [ ] 確認所有環境變數從 `.env` 讀取
5. [ ] 複製到目標位置
6. [ ] 更新 import 路徑（如有需要）
7. [ ] 確認程式碼註釋為英文
8. [ ] 執行基本語法檢查

**檢查清單**：
- [ ] 無 `cloud`、`tenant`、`multi-tenant` 等關鍵字
- [ ] 無硬編碼的 API keys
- [ ] 無硬編碼的資料庫連線字串
- [ ] 所有配置從環境變數讀取
- [ ] 符合本地優先原則
- [ ] 程式碼註釋為英文

**驗證標準**：
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範

---

### 1.3 複製 `playbook_execution.py`

**來源**：`my-agent-mindscape/backend/app/routes/playbook_execution.py`
**目標**：`mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py`

**實作步驟**：
1. [ ] 讀取來源檔案
2. [ ] 檢查並移除所有 cloud/tenant 相關內容
3. [ ] 檢查並移除硬編碼的 API keys
4. [ ] 確認所有環境變數從 `.env` 讀取
5. [ ] 複製到目標位置
6. [ ] 更新 import 路徑（如有需要）
7. [ ] 確認程式碼註釋為英文
8. [ ] 執行基本語法檢查

**檢查清單**：
- [ ] 無 `cloud`、`tenant`、`multi-tenant` 等關鍵字
- [ ] 無硬編碼的 API keys
- [ ] 無硬編碼的資料庫連線字串
- [ ] 所有配置從環境變數讀取
- [ ] 符合本地優先原則
- [ ] 程式碼註釋為英文

**驗證標準**：
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範

---

### 1.4 複製並簡化 `config.py`

**來源**：`my-agent-mindscape/backend/app/routes/config.py`
**目標**：`mindscape-ai-local-core/backend/app/routes/core/config.py`

**實作步驟**：
1. [ ] 讀取來源檔案
2. [ ] 保留 `local` 模式實作
3. [ ] 移除 `remote_crs` 模式的硬編碼實作
4. [ ] 將 `remote_crs` 改為 adapter 模式（回傳 501 或使用 adapter）
5. [ ] 移除硬編碼的 cloud 相關配置
6. [ ] 檢查並移除硬編碼的 API keys
7. [ ] 確認所有環境變數從 `.env` 讀取
8. [ ] 複製到目標位置
9. [ ] 更新 import 路徑（如有需要）
10. [ ] 確認程式碼註釋為英文
11. [ ] 執行基本語法檢查

**檢查清單**：
- [ ] 保留 `local` 模式
- [ ] `remote_crs` 改為 adapter 模式（不寫死在 core）
- [ ] 無硬編碼的 cloud 相關配置
- [ ] 無硬編碼的 API keys
- [ ] 所有配置從環境變數讀取
- [ ] 符合本地優先原則
- [ ] 程式碼註釋為英文

**驗證標準**：
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範
- [ ] `local` 模式可以正常運作
- [ ] `remote_crs` 模式回傳適當錯誤或使用 adapter

---

### 1.5 複製 `system_settings.py`

**來源**：`my-agent-mindscape/backend/app/routes/system_settings.py`
**目標**：`mindscape-ai-local-core/backend/app/routes/core/system_settings.py`

**實作步驟**：
1. [ ] 讀取來源檔案
2. [ ] 檢查並移除所有 cloud/tenant 相關內容
3. [ ] 檢查並移除硬編碼的 API keys
4. [ ] 確認所有環境變數從 `.env` 讀取
5. [ ] 複製到目標位置
6. [ ] 更新 import 路徑（如有需要）
7. [ ] 確認程式碼註釋為英文
8. [ ] 執行基本語法檢查

**檢查清單**：
- [ ] 無 `cloud`、`tenant`、`multi-tenant` 等關鍵字
- [ ] 無硬編碼的 API keys
- [ ] 無硬編碼的資料庫連線字串
- [ ] 所有配置從環境變數讀取
- [ ] 符合本地優先原則
- [ ] 程式碼註釋為英文

**驗證標準**：
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範

---

### 1.6 複製 `tools.py`

**來源**：`my-agent-mindscape/backend/app/routes/tools.py`
**目標**：`mindscape-ai-local-core/backend/app/routes/core/tools.py`

**實作步驟**：
1. [ ] 讀取來源檔案
2. [ ] 確認是「管理器」而非具體 tool 實作
3. [ ] 檢查並移除所有 cloud/tenant 相關內容
4. [ ] 檢查並移除硬編碼的 API keys
5. [ ] 確認所有環境變數從 `.env` 讀取
6. [ ] 複製到目標位置
7. [ ] 更新 import 路徑（如有需要）
8. [ ] 確認程式碼註釋為英文
9. [ ] 執行基本語法檢查

**檢查清單**：
- [ ] 確認是「管理器」而非具體 tool 實作
- [ ] 無 `cloud`、`tenant`、`multi-tenant` 等關鍵字
- [ ] 無硬編碼的 API keys
- [ ] 所有配置從環境變數讀取
- [ ] 符合本地優先原則
- [ ] 程式碼註釋為英文

**驗證標準**：
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範
- [ ] 確認是管理器模式（可以註冊/查詢 tools，但不包含具體 tool 實作）

---

### 1.7 複製 `tool_connections.py`

**來源**：`my-agent-mindscape/backend/app/routes/tool_connections.py`
**目標**：`mindscape-ai-local-core/backend/app/routes/core/tool_connections.py`

**實作步驟**：
1. [ ] 讀取來源檔案
2. [ ] 確認是「管理器」而非具體連線實作
3. [ ] 檢查並移除所有 cloud/tenant 相關內容
4. [ ] 檢查並移除硬編碼的 API keys
5. [ ] 確認所有環境變數從 `.env` 讀取
6. [ ] 複製到目標位置
7. [ ] 更新 import 路徑（如有需要）
8. [ ] 確認程式碼註釋為英文
9. [ ] 執行基本語法檢查

**檢查清單**：
- [ ] 確認是「管理器」而非具體連線實作
- [ ] 無 `cloud`、`tenant`、`multi-tenant` 等關鍵字
- [ ] 無硬編碼的 API keys
- [ ] 所有配置從環境變數讀取
- [ ] 符合本地優先原則
- [ ] 程式碼註釋為英文

**驗證標準**：
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範
- [ ] 確認是管理器模式（可以管理連線，但不包含具體連線實作）

---

### 1.8 更新 `main.py`（第一階段：只註冊 Core Routes）

**目標**：`mindscape-ai-local-core/backend/app/main.py`

**實作步驟**：
1. [ ] 讀取現有 `main.py`
2. [ ] 只 import Layer 0 的 core routes
3. [ ] 移除所有 Layer 2 feature routes 的 import
4. [ ] 實作 `register_core_routes()` 函數，統一註冊 core routes
5. [ ] 確認路由註冊正確
6. [ ] 確認程式碼註釋為英文
7. [ ] 執行基本語法檢查

**實作 Pattern**：

```python
# app/main.py

from fastapi import FastAPI

from app.routes.core import (
    workspace,
    playbook,
    playbook_execution,
    config,
    system_settings,
    tools,
    tool_connections,
)

app = FastAPI()

def register_core_routes(app: FastAPI) -> None:
    """Register Layer 0 kernel routes"""
    app.include_router(workspace.router, prefix="/api/workspaces", tags=["workspace"])
    app.include_router(playbook.router, prefix="/api/playbooks", tags=["playbook"])
    app.include_router(playbook_execution.router, prefix="/api/playbooks", tags=["playbook"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(system_settings.router, prefix="/api/system", tags=["system"])
    app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
    app.include_router(tool_connections.router, prefix="/api/tool-connections", tags=["tools"])

register_core_routes(app)

# Note: Layer 2 feature routes will be registered via pack_registry in Phase 3.5
```

**檢查清單**：
- [ ] 只 import Layer 0 的 core routes
- [ ] 無 Layer 2 feature routes 的 import
- [ ] 使用 `register_core_routes()` 函數統一註冊
- [ ] 路由註冊正確
- [ ] 程式碼註釋為英文
- [ ] 預留 pack registry 註冊的註解說明

**驗證標準**：
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範
- [ ] 應用可以啟動（`docker compose up`）
- [ ] 可以訪問核心 API 端點

---

## Phase 2: Layer 1 - Core Primitives（管理器寫死，內容可插拔）

**狀態**：✅ 第一階段（stub）已完成，❌ 第二階段（adapter）待實作

### 2.1 複製 `vector_db.py`（第一階段：先上 Stub）

**狀態**：✅ 已完成（stub 實現）

**來源**：`my-agent-mindscape/backend/app/routes/vector_db.py`
**目標**：`mindscape-ai-local-core/backend/app/routes/core/vector_db.py`

**實作策略**：分兩階段實作，避免在 Routes 大搬家同時還 debug DB 連線

**第一階段（本次遷移）**：先建立乾淨的 stub
**第二階段（後續）**：實作 adapter 並接上具體 DB

**實作步驟（第一階段）**：
1. [x] 讀取來源檔案
2. [ ] 實作 `VectorStorePort` 介面（如尚未存在）⚠️ **待第二階段**
3. [x] 建立乾淨的 stub 實作（只回 501，不做任何 DB 操作）
4. [x] 移除硬編碼的 Postgres 依賴
5. [x] 檢查並移除所有 cloud/tenant 相關內容
6. [x] 檢查並移除硬編碼的 API keys
7. [x] 確認所有環境變數從 `.env` 讀取
8. [x] 複製到目標位置
9. [x] 更新 import 路徑（如有需要）
10. [x] 確認程式碼註釋為英文
11. [x] 執行基本語法檢查

**Stub 實作範例**：

```python
# app/routes/core/vector_db.py

from fastapi import APIRouter, HTTPException
from app.core.ports.vector_store import VectorStorePort

router = APIRouter()

@router.get("/vector-db/status")
async def get_vector_db_status():
    """Get vector database status"""
    # Stub: Always return 501 until adapter is implemented
    raise HTTPException(
        status_code=501,
        detail="Vector database adapter not configured. Please install and configure a vector store adapter."
    )

# Note: Adapter implementation will be added in a later phase
```

**檢查清單**：
- [ ] 實作 `VectorStorePort` 介面（或確認已存在）⚠️ **待第二階段**
- [x] 建立乾淨的 stub（只回 501）
- [x] 移除硬編碼的 Postgres 依賴
- [x] 無 `cloud`、`tenant`、`multi-tenant` 等關鍵字
- [x] 無硬編碼的 API keys
- [x] 所有配置從環境變數讀取
- [x] 符合本地優先原則
- [x] 程式碼註釋為英文

**驗證標準**：
- [x] 檔案可以正常 import
- [x] 無語法錯誤
- [x] 符合 PEP 8 規範
- [x] 無 adapter 時回 501
- [x] 不包含任何實際 DB 操作

**後續階段（待實作）**：
- [ ] ⚠️ **實作 adapter 模式**
- [ ] ⚠️ **接上具體的向量資料庫**（Postgres+pgvector / Weaviate / local-FAISS）
- [ ] ⚠️ **有 adapter 時可以正常運作**

---

### 2.2 複製 `vector_search.py`（第一階段：先上 Stub）

**狀態**：✅ 已完成（stub 實現），⚠️ 路由前綴需修正為 `/api/v1/vector`

**來源**：`my-agent-mindscape/backend/app/routes/vector_search.py`
**目標**：`mindscape-ai-local-core/backend/app/routes/core/vector_search.py`

**實作策略**：分兩階段實作，與 `vector_db.py` 相同

**第一階段（本次遷移）**：✅ 先建立乾淨的 stub
**第二階段（後續）**：❌ 實作 adapter 並接上具體 DB

**實作步驟（第一階段）**：
1. [x] 讀取來源檔案
2. [ ] 使用 `VectorStorePort` 介面（確認已存在）⚠️ **待第二階段**
3. [x] 建立乾淨的 stub 實作（只回 501，不做任何 DB 操作）
4. [x] 檢查並移除所有 cloud/tenant 相關內容
5. [x] 檢查並移除硬編碼的 API keys
6. [x] 確認所有環境變數從 `.env` 讀取
7. [x] 複製到目標位置
8. [x] 更新 import 路徑（如有需要）
9. [x] 確認程式碼註釋為英文
10. [x] 執行基本語法檢查
11. [ ] ⚠️ **修正路由前綴為 `/api/v1/vector`**（目前是 `/api/vector`）

**Stub 實作範例**：

```python
# app/routes/core/vector_search.py

from fastapi import APIRouter, HTTPException
from app.core.ports.vector_store import VectorStorePort

router = APIRouter()

@router.post("/vector-search")
async def vector_search(query: str):
    """Perform vector search"""
    # Stub: Always return 501 until adapter is implemented
    raise HTTPException(
        status_code=501,
        detail="Vector database adapter not configured. Please install and configure a vector store adapter."
    )

# Note: Adapter implementation will be added in a later phase
```

**檢查清單**：
- [ ] 使用 `VectorStorePort` 介面（確認已存在）⚠️ **待第二階段**
- [x] 建立乾淨的 stub（只回 501）
- [x] 無 `cloud`、`tenant`、`multi-tenant` 等關鍵字
- [x] 無硬編碼的 API keys
- [x] 所有配置從環境變數讀取
- [x] 符合本地優先原則
- [x] 程式碼註釋為英文
- [ ] ⚠️ **路由前綴統一為 `/api/v1/vector`**

**驗證標準**：
- [x] 檔案可以正常 import
- [x] 無語法錯誤
- [x] 符合 PEP 8 規範
- [x] 無 adapter 時回 501
- [x] 不包含任何實際 DB 操作

**後續階段（待實作）**：
- [ ] ⚠️ **實作 adapter 模式**
- [ ] ⚠️ **接上具體的向量資料庫**
- [ ] ⚠️ **有 adapter 時可以正常運作**

---

### 2.3 複製並重構 `capability_packs.py`

**狀態**：✅ 已完成

**來源**：`my-agent-mindscape/backend/app/routes/capability_packs.py`
**目標**：`mindscape-ai-local-core/backend/app/routes/core/capability_packs.py`

**實作步驟**：
1. [x] 讀取來源檔案
2. [x] 改為 registry API（列出 / 啟用 / 停用 packs）
3. [x] 移除硬編碼的 pack 清單
4. [x] 改為從 `/packs/*.yaml` 或 plugin registry 讀取
5. [x] 實作 pack 掃描功能
6. [x] 檢查並移除所有 cloud/tenant 相關內容
7. [x] 檢查並移除硬編碼的 API keys
8. [x] 確認所有環境變數從 `.env` 讀取
9. [x] 複製到目標位置
10. [x] 更新 import 路徑（如有需要）
11. [x] 確認程式碼註釋為英文
12. [x] 執行基本語法檢查

**檢查清單**：
- [x] 改為 registry API（列出 / 啟用 / 停用 packs）
- [x] 移除硬編碼的 pack 清單
- [x] 改為從 `/packs/*.yaml` 或 plugin registry 讀取
- [x] 無 `cloud`、`tenant`、`multi-tenant` 等關鍵字
- [x] 無硬編碼的 API keys
- [x] 所有配置從環境變數讀取
- [x] 符合本地優先原則
- [x] 程式碼註釋為英文

**驗證標準**：
- [x] 檔案可以正常 import
- [x] 無語法錯誤
- [x] 符合 PEP 8 規範
- [x] 可以列出 packs
- [x] 可以啟用/停用 packs
- [x] 可以從 `/packs/*.yaml` 讀取 pack 定義

---

## Phase 3: Layer 2 - Domain/UX Features（全部 plug-in 化）

### 3.1 建立 features 目錄結構

**實作步驟**：
1. [ ] 建立 `backend/features/` 目錄
2. [ ] 為每個 feature 建立子目錄
3. [ ] 確認目錄結構符合規範

**目錄結構**：
```
backend/features/
├── agent/
├── ai_roles/
├── core_export/
├── external_docs/
├── habits/
├── playbook_indexing/
├── playbook_personalization/
├── review/
├── workflow_templates/
├── course_production/
└── mindscape/
```

**檢查清單**：
- [ ] `backend/features/` 目錄已建立
- [ ] 所有 feature 子目錄已建立
- [ ] 目錄結構符合規範

---

### 3.2 遷移 feature routes（11 個檔案）

**重要約定**：每個 feature routes module 必須 export 一個 `router: APIRouter`，作為統一介面供 `pack_registry` 使用。

**實作步驟**（每個檔案）：
1. [ ] 讀取來源檔案
2. [ ] 檢查並移除所有 cloud/tenant 相關內容
3. [ ] 檢查並移除硬編碼的 API keys
4. [ ] 確認所有環境變數從 `.env` 讀取
5. [ ] 確認 export 一個 `router: APIRouter` 物件
6. [ ] 複製到目標位置
7. [ ] 更新 import 路徑（如有需要）
8. [ ] 確認程式碼註釋為英文
9. [ ] 執行基本語法檢查

**統一介面範例**：

```python
# backend/features/habits/routes.py

from fastapi import APIRouter

router = APIRouter()

@router.get("/habits")
async def list_habits():
    """List all habits"""
    # ...

@router.post("/habits")
async def create_habit():
    """Create a new habit"""
    # ...

# Note: This module must export a 'router' object for pack_registry to discover
```

**檔案清單**：
- [ ] `agent.py` → `backend/features/agent/routes.py`
- [ ] `ai_roles.py` → `backend/features/ai_roles/routes.py`
- [ ] `core_export.py` → `backend/features/core_export/routes.py`
- [ ] `external_docs.py` → `backend/features/external_docs/routes.py`
- [ ] `habits.py` → `backend/features/habits/routes.py`
- [ ] `playbook_indexing.py` → `backend/features/playbook_indexing/routes.py`
- [ ] `playbook_personalization.py` → `backend/features/playbook_personalization/routes.py`
- [ ] `review.py` → `backend/features/review/routes.py`
- [ ] `workflow_templates.py` → `backend/features/workflow_templates/routes.py`
- [ ] `course_production/*` → `backend/features/course_production/`
- [ ] `mindscape.py` → `backend/features/mindscape/routes.py`

**檢查清單**（每個檔案）：
- [ ] 無 `cloud`、`tenant`、`multi-tenant` 等關鍵字
- [ ] 無硬編碼的 API keys
- [ ] 所有配置從環境變數讀取
- [ ] 符合本地優先原則
- [ ] **必須 export 一個 `router: APIRouter` 物件**
- [ ] 程式碼註釋為英文
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範

---

### 3.3 建立 pack metadata 檔案

**實作步驟**：
1. [ ] 為每個 feature 建立對應的 `pack.yaml`
2. [ ] 定義 pack 的 metadata（id, name, description, enabled_by_default）
3. [ ] 定義 pack 的 routes、playbooks、tools
4. [ ] 確認 YAML 格式正確

**Pack YAML 範例**：

```yaml
# backend/packs/habits-pack.yaml

id: habits
name: "Habits & Daily Routines"
enabled_by_default: true
description: "Let Workspace suggest and track small daily learning / writing habits."

routes:
  - "backend.features.habits.routes:router"

playbooks:
  - "daily_planning"
  - "habit_reflection"

tools:
  - "habit_storage"
```

**檔案清單**：
- [ ] `backend/packs/agent-pack.yaml`
- [ ] `backend/packs/ai-roles-pack.yaml`
- [ ] `backend/packs/core-export-pack.yaml`
- [ ] `backend/packs/external-docs-pack.yaml`
- [ ] `backend/packs/habits-pack.yaml`
- [ ] `backend/packs/playbook-indexing-pack.yaml`
- [ ] `backend/packs/playbook-personalization-pack.yaml`
- [ ] `backend/packs/review-pack.yaml`
- [ ] `backend/packs/workflow-templates-pack.yaml`
- [ ] `backend/packs/course-production-pack.yaml`
- [ ] `backend/packs/mindscape-pack.yaml`

**特別說明：mindscape-pack.yaml**

`mindscape-pack` 是 Mindscape AI local-core 的預設能力包。它被實作為一個普通的 pack（沒有特殊權限），但預設啟用。

```yaml
# backend/packs/mindscape-pack.yaml

id: mindscape
name: "Mindscape Core"
enabled_by_default: true
description: "Default capability pack shipped with Mindscape AI local core. Provides core Mindscape management functionality."

routes:
  - "backend.features.mindscape.routes:router"

playbooks:
  - "mindscape_setup"
  - "mindscape_sync"

tools:
  - "mindscape_storage"
```

**檢查清單**：
- [ ] 所有 pack.yaml 已建立
- [ ] YAML 格式正確
- [ ] 定義了 metadata（id, name, description, enabled_by_default）
- [ ] 定義了 routes、playbooks、tools
- [ ] pack ID 唯一且符合命名規範
- [ ] routes 使用標準格式：`"module.path:router"`
- [ ] mindscape-pack 有特別註解說明其定位

---

### 3.4 實作 Pack Registry Loader

**目標**：`mindscape-ai-local-core/backend/app/core/pack_registry.py`

**實作步驟**：
1. [ ] 建立 `pack_registry.py`
2. [ ] 實作掃描 `/packs/*.yaml` 的功能
3. [ ] 實作動態載入 routes 的功能（使用標準介面：`module.path:router`）
4. [ ] 實作啟用/停用 pack 的功能
5. [ ] 確認程式碼註釋為英文
6. [ ] 執行基本語法檢查

**實作範例**：

```python
# app/core/pack_registry.py

import importlib
from pathlib import Path
from typing import List, Dict
from fastapi import FastAPI, APIRouter
import yaml

def load_pack_yaml(pack_path: Path) -> Dict:
    """Load pack metadata from YAML file"""
    with open(pack_path, 'r') as f:
        return yaml.safe_load(f)

def load_router_from_string(import_string: str) -> APIRouter:
    """Load router from import string (e.g., 'backend.features.habits.routes:router')"""
    module_path, attr_name = import_string.split(':')
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)

def load_and_register_packs(app: FastAPI, packs_dir: Path = Path("backend/packs")) -> None:
    """Scan packs directory and register enabled packs"""
    enabled_packs = []

    for pack_file in packs_dir.glob("*.yaml"):
        pack_meta = load_pack_yaml(pack_file)

        # Check if pack is enabled (by default or explicitly)
        if pack_meta.get("enabled_by_default", False):
            enabled_packs.append(pack_meta)

    # Register routes for enabled packs
    for pack in enabled_packs:
        for route_import in pack.get("routes", []):
            router = load_router_from_string(route_import)
            prefix = f"/api/features/{pack['id']}"
            app.include_router(router, prefix=prefix, tags=[pack['id']])
```

**檢查清單**：
- [ ] 可以掃描 `/packs/*.yaml`
- [ ] 可以動態載入 routes（使用標準介面：`module.path:router`）
- [ ] 可以啟用/停用 pack
- [ ] 支援 `enabled_by_default` 欄位
- [ ] 程式碼註釋為英文
- [ ] 符合本地優先原則

**驗證標準**：
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範
- [ ] 可以掃描並載入 packs
- [ ] 可以啟用/停用 packs
- [ ] 可以正確載入並註冊 feature routes

---

### 3.5 更新 `main.py` 使用 Pack Registry（第二階段：整合 Pack Routes）

**目標**：`mindscape-ai-local-core/backend/app/main.py`

**實作步驟**：
1. [ ] 讀取現有 `main.py`（應已包含 Phase 1.8 的 `register_core_routes()`）
2. [ ] import `pack_registry` 模組
3. [ ] 在 startup 時呼叫 `load_and_register_packs(app)`
4. [ ] 確認 core routes 和 pack routes 不會互相衝突
5. [ ] 確認程式碼註釋為英文
6. [ ] 執行基本語法檢查

**完整實作 Pattern**：

```python
# app/main.py

from fastapi import FastAPI

from app.routes.core import (
    workspace,
    playbook,
    playbook_execution,
    config,
    system_settings,
    tools,
    tool_connections,
)
from app.core.pack_registry import load_and_register_packs

app = FastAPI()

def register_core_routes(app: FastAPI) -> None:
    """Register Layer 0 kernel routes"""
    app.include_router(workspace.router, prefix="/api/workspaces", tags=["workspace"])
    app.include_router(playbook.router, prefix="/api/playbooks", tags=["playbook"])
    app.include_router(playbook_execution.router, prefix="/api/playbooks", tags=["playbook"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(system_settings.router, prefix="/api/system", tags=["system"])
    app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
    app.include_router(tool_connections.router, prefix="/api/tool-connections", tags=["tools"])

# Phase 1: Register core routes (Layer 0)
register_core_routes(app)

# Phase 3: Register feature routes via pack registry (Layer 2)
load_and_register_packs(app)
```

**檢查清單**：
- [ ] 保留 Phase 1.8 的 `register_core_routes()` 函數
- [ ] import `pack_registry` 模組
- [ ] 在 startup 時呼叫 `load_and_register_packs(app)`
- [ ] core routes 和 pack routes 不會互相衝突
- [ ] 程式碼註釋為英文

**驗證標準**：
- [ ] 檔案可以正常 import
- [ ] 無語法錯誤
- [ ] 符合 PEP 8 規範
- [ ] 應用可以啟動
- [ ] 可以訪問 core routes
- [ ] 可以動態載入並訪問 feature routes

---

## Phase 4: 驗證與測試

### 4.1 驗證核心功能

**驗證項目**：
- [ ] Workspace 可以建立/列表/取得
- [ ] Playbook 可以列表/執行
- [ ] Config 可以設定/讀取

**測試步驟**：
1. [ ] 啟動服務（`docker compose up -d`）
2. [ ] 測試 Workspace API
3. [ ] 測試 Playbook API
4. [ ] 測試 Config API
5. [ ] 確認所有測試通過

---

### 4.2 驗證 Core Primitives

**驗證項目**：
- [ ] Tools 可以註冊/查詢
- [ ] Vector DB 可以配置（如果啟用 adapter）
- [ ] Capability Packs 可以列出/啟用/停用

**測試步驟**：
1. [ ] 測試 Tools API
2. [ ] 測試 Vector DB API（如有 adapter）
3. [ ] 測試 Capability Packs API
4. [ ] 確認所有測試通過

---

### 4.3 驗證 Feature Modules

**驗證項目**：
- [ ] 可以透過 pack registry 載入 feature routes
- [ ] 可以啟用/停用 feature packs
- [ ] 未啟用的 feature 不會出現在 API

**測試步驟**：
1. [ ] 測試 pack registry 載入
2. [ ] 測試啟用/停用 feature packs
3. [ ] 確認未啟用的 feature 不會出現在 API
4. [ ] 確認所有測試通過

---

### 4.4 驗證 Docker 部署

**驗證項目**：
- [ ] 按照 GitHub 文檔流程測試
- [ ] 確認所有服務可以正常啟動
- [ ] 確認前端可以正常連接後端

**測試步驟**：
1. [ ] 按照 GitHub 文檔流程測試
2. [ ] 確認所有服務可以正常啟動
3. [ ] 確認前端可以正常連接後端
4. [ ] 確認所有測試通過

---

## 📝 通用檢查清單

### 程式碼品質

- [ ] 符合 PEP 8 規範
- [ ] 程式碼註釋為英文
- [ ] 無語法錯誤
- [ ] 無未使用的 import
- [ ] 無未使用的變數

### 安全檢查

- [ ] 無硬編碼的 API keys
- [ ] 無硬編碼的密碼
- [ ] 所有敏感資訊從環境變數讀取
- [ ] `.env` 文件不在 Git 中

### 架構檢查

- [ ] 無 cloud/tenant 相關內容（core routes）
- [ ] 符合本地優先原則
- [ ] 符合 Port/Adapter 架構原則
- [ ] 所有依賴都是可選的或可插拔的

### 文檔檢查

- [ ] 更新 `ROUTES_CLASSIFICATION.md` 標記完成項目
- [ ] 更新相關架構文檔
- [ ] 更新 README 說明新的目錄結構

---

## 🔄 實作流程

1. **讀取來源檔案** → 檢查內容
2. **移除不符合規範的內容** → cloud/tenant、硬編碼 API keys
3. **調整架構** → adapter 模式、plug-in 化
4. **複製到目標位置** → 更新 import 路徑
5. **檢查程式碼品質** → PEP 8、註釋、語法
6. **驗證功能** → 測試 API、確認運作正常
7. **更新文檔** → 標記完成項目

---

## ⚠️ 注意事項

1. **遵守開發規範**
   - 所有程式碼註釋使用英文（i18n 基底）
   - 內部文檔使用繁體中文
   - 嚴禁硬編碼敏感資訊
   - 嚴禁破壞本地優先原則

2. **檢查清單**
   - [ ] 確認無 cloud/tenant 相關內容
   - [ ] 確認無硬編碼的 API keys
   - [ ] 確認所有依賴都是可選的或可插拔的
   - [ ] 確認符合 Port/Adapter 架構原則

3. **文檔更新**
   - [ ] 更新 `ROUTES_CLASSIFICATION.md` 標記完成項目
   - [ ] 更新相關架構文檔
   - [ ] 更新 README 說明新的目錄結構

---

**最後更新**：2025-12-02

