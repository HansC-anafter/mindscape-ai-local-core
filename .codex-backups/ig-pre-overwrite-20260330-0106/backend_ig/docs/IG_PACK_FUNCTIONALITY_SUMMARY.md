# IG Pack 功能清單 - 快速參考

**建立日期**: 2026-01-17
**最後更新**: 2026-01-20

---

## 功能統計

| 類別 | 數量 | 說明 |
|------|------|------|
| **Playbooks** | 18 | 工作流程定義 |
| **Tools** | 20 | 工具函式實作 |
| **Services** | 20 | 服務模組實作 |
| **UI Components (manifest 註冊)** | 3 | UI 入口元件（`IGWorkbenchPage`, `ig_posts_grid_view`, `ig_following_analyzer`） |
| **總計** | 63 | 程式碼檔案 |

---

## Playbooks 清單（18 個）

### 內容建立（3 個）
| Playbook Code | Display Name | 功能描述 | 語系 | UI 元件 |
|--------------|--------------|----------|------|--------|
| `ig_post_generation` | IG Post Generation | 生成 Instagram 貼文 | zh-TW, en | 是（IGWorkbench / GridView） |
| `ig_template_engine` | Template Engine | 應用模板生成多個變體 | zh-TW, en, ja | 部分（IGWorkbench；produce 模組尚未完整覆蓋） |
| `ig_content_reuse` | Content Reuse | 內容格式轉換與復用 | zh-TW, en, ja | 部分（IGWorkbench；缺內容轉換專用 UI） |

### 內容管理（4 個）
| Playbook Code | Display Name | 功能描述 | 語系 | UI 元件 |
|--------------|--------------|----------|------|--------|
| `ig_hashtag_manager` | Hashtag Manager | 管理 hashtag 分組與組合 | zh-TW, en, ja | 是（IGWorkbench / HashtagPanel） |
| `ig_asset_manager` | Asset Manager | 管理 IG Post 資產（命名、尺寸、格式） | zh-TW, en, ja | 部分（IGWorkbench；assets 模組目前為 placeholder） |
| `ig_series_manager` | Series Manager | 管理 IG Post 系列與進度追蹤 | zh-TW, en, ja | 是（IGWorkbench / SeriesPanel） |
| `ig_vault_structure_manager` | Vault Structure Manager | 管理工作區結構 | zh-TW, en, ja | 部分（IGWorkbench；assets 模組目前為 placeholder） |

### 內容工作流程（7 個）
| Playbook Code | Display Name | 功能描述 | 語系 | UI 元件 |
|--------------|--------------|----------|------|--------|
| `ig_review_system` | Review System | 管理審查工作流程與決策日誌 | zh-TW, en, ja | 部分（IGWorkbench / ReviewPanel；需補齊決策閉環） |
| `ig_interaction_templates` | Interaction Templates | 管理互動模板（評論回覆、DM） | zh-TW, en, ja | 部分（IGWorkbench / EngagePanel） |
| `ig_metrics_backfill` | Metrics Backfill | 管理發布後指標與資料分析 | zh-TW, en, ja | 部分（IGWorkbench / MeasurePanel） |
| `ig_batch_processor` | Batch Processor | 批次處理多個貼文 | zh-TW, en, ja | 部分（IGWorkbench；目前主要由 Execution Control 觸發） |
| `ig_complete_workflow` | Complete Workflow | 編排多個 playbook 執行完整工作流程 | zh-TW, en, ja | 部分（IGWorkbench；缺 workflow 可視化） |
| `ig_content_checker` | Content Checker | 檢查內容合規性（醫療/投資聲明、版權） | zh-TW, en, ja | 部分（IGWorkbench；Execution Control / ReviewPanel） |
| `ig_export_pack_generator` | Export Pack Generator | 生成匯出包（post.md、hashtags.txt） | zh-TW, en, ja | 部分（IGWorkbench / ExportPanel） |
| `ig_frontmatter_validator` | Frontmatter Validator | 驗證 frontmatter 與計算準備度分數 | zh-TW, en, ja | 部分（IGWorkbench / ReadyScore） |

### 內容整合（2 個）
| Playbook Code | Display Name | 功能描述 | 語系 | UI 元件 |
|--------------|--------------|----------|------|--------|
| `ig_sync_content` | Sync Content | 從 Instagram 拉取 posts/reels/stories | zh-TW, en | 部分（IGWorkbench；尚缺 sync 專用 UI） |
| `ig_publish_content` | Publish Content | 發布內容到 Instagram（photo/reel/carousel） | zh-TW, en | 是（IGWorkbench / PublishPanel） |

### 內容分析（1 個）
| Playbook Code | Display Name | 功能描述 | 語系 | UI 元件 |
|--------------|--------------|----------|------|--------|
| `ig_analyze_following` | Following Analyzer | 提取追蹤列表並分析帳號頁面 | zh-TW, en | 是（FollowingAnalyzer / IGWorkbench Accounts） |

---

## Tools 清單（20 個）

### 內容建立工具（1 個）
- `ig_post_style_analyzer` - 分析 IG 貼文視覺風格

### 管理工具（5 個）
- `ig_hashtag_manager_tool` - Hashtag 管理
- `ig_template_engine_tool` - 模板引擎
- `ig_asset_manager_tool` - 資產管理
- `ig_series_manager_tool` - 系列管理
- `ig_vault_structure_tool` - 工作區結構管理

### 工作流程工具（8 個）
- `ig_review_system_tool` - 審查系統
- `ig_interaction_templates_tool` - 互動模板
- `ig_metrics_backfill_tool` - 指標回填
- `ig_content_reuse_tool` - 內容復用
- `ig_batch_processor_tool` - 批次處理
- `ig_complete_workflow_tool` - 完整工作流程
- `ig_content_checker_tool` - 內容檢查
- `ig_export_pack_generator_tool` - 匯出包生成
- `ig_frontmatter_validator_tool` - Frontmatter 驗證

### 整合工具（5 個）
- `ig_fetch_posts` - 拉取 posts
- `ig_fetch_reels` - 拉取 reels
- `ig_fetch_stories` - 拉取 stories
- `ig_validate_media` - 驗證媒體檔案
- `ig_publish_post` - 發布內容

### 分析工具（1 個）
- `ig_analyze_following` - 追蹤列表分析（Playwright）

---

## Services 清單（20 個）

### 核心服務（3 個）
- `instagram_api_client.py` - Instagram Graph API 客戶端
- `site_hub_client.py` - Site-hub 客戶端
- `workspace_storage.py` - 工作區儲存管理

### 功能服務（17 個）
- `asset_manager.py` - 資產管理
- `batch_processor.py` - 批次處理
- `complete_workflow.py` - 完整工作流程
- `content_checker.py` - 內容檢查
- `content_reuse.py` - 內容復用
- `control_plane_registry.py` - 控制平面注册表
- `export_pack_generator.py` - 匯出包生成
- `frontmatter_schema.py` - Frontmatter 模式定义
- `frontmatter_validator.py` - Frontmatter 驗證
- `hashtag_manager.py` - Hashtag 管理
- `interaction_templates.py` - 互動模板
- `metrics_backfill.py` - 指標回填
- `review_system.py` - 審查系統
- `run_tracker.py` - 运行跟踪
- `series_manager.py` - 系列管理
- `template_engine.py` - 模板引擎
- `vault_structure.py` - 工作區結構

---

## UI Components 清單（3 個已註冊）

| Component Code | 路徑 | 功能描述 | 路由 | 關聯 Playbook |
|----------------|------|----------|------|---------------|
| `IGWorkbenchPage` | `ui/IGWorkbench.tsx` | Unified Workbench (modules + content views + execution control) |（由 Workspaces extension/mount 決定）| `ig_*`（含 `ig_capture_account_snapshot`） |
| `ig_posts_grid_view` | `ui/IGGridViewModal.tsx` | IG Posts Grid View and Timeline View | `/workspaces/{workspace_id}/ig-posts` | `ig_post_generation` |
| `ig_following_analyzer` | `ui/IGFollowingAnalyzer.tsx` | Following List Analyzer with real-time progress | `/workspaces/{workspace_id}/ig-following-analyzer` | `ig_analyze_following` |

**註**: `capabilities/ig/ui/**` 已包含 Workbench 與 modules（不再僅 5 個檔案）。本摘要以 `manifest.yaml:ui_components` 為 UI 入口真源。

---

## 缺失 / 不足 UI 的 Playbook（以「閉環 UX」為準）

以下項目屬於「已被 IGWorkbench 納入 `playbook_codes`，但仍缺模組/表單/結果視圖」：

- `ig_asset_manager` / `ig_vault_structure_manager`：Workbench `assets` 模組目前為 placeholder，缺 AssetsPanel。
- `ig_template_engine`：缺模板清單/套用閉環（目前僅有零散對話框元件）。
- `ig_content_reuse`：缺內容轉換專用 UI。
- `ig_sync_content`：缺同步內容專用 UI（account 選取 + posts/reels/stories + 同步結果展示）。
- `ig_complete_workflow`：缺 workflow 可視化與 preset UX。
- `ig_batch_processor`：缺批次範圍選取（filtered/batch）與結果摘要視圖。

專項規劃與實作 TODO 參考：`capabilities/ig/docs/todos/IG_MISSING_UI_PLAYBOOKS_IMPLEMENTATION_TODOS_2026-01-20.md`

---

## 功能依賴關係

### 核心工作流程路徑
```
內容建立
  └─ ig_post_generation
      ├─ ig_hashtag_manager (可選)
      ├─ ig_template_engine (可選)
      ├─ ig_asset_manager (可選)
      └─ ig_series_manager (可選)
          │
          ├─ ig_content_checker
          ├─ ig_frontmatter_validator
          │   │
          │   └─ ig_review_system
          │       └─ ig_export_pack_generator
          │           │
          │           └─ ig_publish_content (整合)
          │
          └─ ig_batch_processor (批次)
              └─ ig_complete_workflow (編排)
```

### 內容復用途徑
```
ig_content_reuse
  ├─ 長文章 → 輪播
  ├─ 輪播 → Reel
  └─ Reel → Stories
```

### 內容整合路徑
```
內容同步
  └─ ig_sync_content
      ├─ ig_fetch_posts
      ├─ ig_fetch_reels
      └─ ig_fetch_stories

內容發布
  └─ ig_publish_content
      ├─ ig_validate_media
      └─ ig_publish_post
```

### 內容分析路徑
```
ig_analyze_following (Playwright)
  └─ 提取追蹤列表
      └─ 訪問帳號頁面
          └─ 統計資料
```

#### 執行可靠性與進度可視（2026-01-19 落地）
- **進度 artifact**：`ig_analyze_following_progress` 會隨執行持續更新（UI 可用 `updated_at` 判定 stale）
- **trace_id 對齊**：缺省時使用 `execution_id` 作為 trace fallback，避免 progress「寫了但 UI 對不上」
- **滾動相容 IG 虛擬化列表**：強制 wheel/scroll 事件 + 以新增帳號數判定繼續滾動，避免只抓到首屏（例如 12）就結束
- **帳號頁 hard timeout**：預設 90s（`IG_ACCOUNT_PAGE_TIMEOUT_SEC`）防止卡死導致進度停更
- **IG profile 鎖**：同一 `user_data_dir` 同時只允許一個 IG 自動化任務（Runner 透過 `runner_locks` 管理）

#### 執行控制與可重跑語義（2026-01-20 更新）
- **明確 `run_mode`**：`full | list | visit`，用來明確本次 run 的意圖（避免隱式/比例/魔數導致「未達 expected 就跳階段」）
  - `full`：滾動抓取清單；若 `visit_account_pages=true`，在滿足前置條件後繼續訪問頁面
  - `list`：只抓清單（強制 `visit_account_pages=false`）
  - `visit`：只訪問頁面（強制 `visit_account_pages=true`，且會復用已保存清單；若沒有可用清單會報錯提示先跑 `list`）
- **list_capture_status（清單捕獲狀態）**：對「是否真的跑滿 / 是否 UI 已窮盡」給出可驗證結論
  - `full`：達到 `expected_following_count`（嚴格等於/大於，不用比例）
  - `exhausted_incomplete`：已證據化判定 UI 已無法再載入，但清單仍小於 expected
  - `interrupted_incomplete / blocked / unknown_incomplete`：中斷、阻擋或不明原因未滿
- **exhausted 仍可接著 visit**：當 `list_capture_status=exhausted_incomplete` 且 `visit_account_pages=true` 時，允許繼續訪問頁面（因為 UI 已證明吐不出更多）
- **Workbench 側邊欄 Execution Debug**：
  - **即時更新**：SSE + 輪詢 fallback，避免必須手動 Refresh 才更新
  - **saved（dedup）**：顯示 workspace 歷史落檔去重後的累積帳號數，協助解釋「本輪 targets vs 已保存清單」
  - **操作按鈕**：Cancel、Rerun、Rerun (list only)、Rerun (visit pages)（包含 succeeded/completed_partial 的可重跑）
- **Debug 截圖 API**：新增 `GET /api/v1/playbooks/execute/{execution_id}/debug/screenshot?file=...`（用於在 UI 開啟滾動 debug 截圖）

---

## 產品化建議

### 方案對比

| 方案 | 優點 | 缺點 | 適用場景 |
|------|------|------|----------|
| **統一 Workbench** | 一站式存取所有功能<br>統一體驗<br>易於導覽 | 介面可能複雜<br>需要大量開發 | 功能豐富、使用者需要頻繁切換 |
| **分類工作台** | 介面清晰<br>功能聚焦<br>漸進式開發 | 需要多頁面跳轉<br>使用者體驗分割 | 功能分類明確、使用情境固定 |
| **混合方案** | 兼顧靈活性與聚焦<br>重點功能突出 | 需要維護多套介面 | 部分功能常用、部分偶爾使用 |

### 推薦架構

**建議採用混合方案**：

1. **主 Workbench**（入口）
   - 展示所有 Playbook 分類
   - 提供快速執行入口
   - 顯示最近執行記錄
   - 整合現有 UI 元件（GridView、FollowingAnalyzer）

2. **重點功能工作台**（專用介面）
   - `ig_post_generation` - 內容建立工作台
   - `ig_publish_content` - 內容發布工作台
   - `ig_analyze_following` - 分析工作台（已有）

3. **Playbook 執行介面**（通用）
   - 其他 Playbook 透過通用執行介面存取
   - 支援參數設定與結果展示

---

**文件路徑**: `mindscape-ai-cloud/capabilities/ig/docs/IG_PACK_FUNCTIONALITY_INVENTORY.md`
**詳細功能說明**: 請參閱完整功能清單文件
