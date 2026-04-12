## 目標

讓 `ig_analyze_following` 的 **visiting_pages 可續跑**，達成：

- **先跑一輪拿到 accounts 名單**（scrolling）
- 後續任務（或 rerun）即使前一輪在 visiting_pages 卡死/被 runner reaper 標 failed，也能：
  - **直接沿用已抓到的 accounts 名單**
  - **跳過 scrolling**
  - **只補跑尚未分析完成（或曾失敗）的帳號頁**

此機制的核心是：把「名單」視為可重用的 artifact，並把 visiting_pages 變成可重入的 stage。

---

## 資料來源（名單從哪裡來）

我們使用 workspace artifacts 中的 progress artifact：

- `playbook_code == ig_analyze_following`
- `artifact.metadata.source == ig_analyze_following_progress`
- `artifact.content.accounts`：accounts 名單（含 `username/account_link` 與可能的 `page_analyzed_at/page_analysis_error`）
- `artifact.content.metadata`：
  - `target_username`
  - `source_profile_ref`（user_data_dir）
  - `expected_following_count`
  - `total_accounts`
  - 其他 scroll/debug 元資料

**選取規則（Resume Artifact Selection）**

在 `capabilities/ig/tools/following_analyzer/runner.py` 中，resume 只會挑選符合下列條件的最新 progress artifact：

- `workspace_id` 相同
- `target_username` 相同
- `source_profile_ref == user_data_dir` 相同（避免拿錯登入帳號/瀏覽器 profile 的名單）
- 依 `updated_at` 最新優先

---

## 續跑行為（實作規格）

### 何時啟用

當符合以下條件時，會啟用 visiting_pages 續跑：

- `visit_account_pages == true`
- `IG_RESUME_VISIT_PAGES != 0`（預設啟用）
- workspace 中存在「符合 selection 規則」的 progress artifact
- progress artifact 中 accounts 數量達到下限：`len(accounts) >= IG_RESUME_MIN_ACCOUNTS`（預設 30）

### 啟用後做什麼

1. **載入 accounts**：從 progress artifact 讀取 `content.accounts`
2. **正規化 accounts**
   - 去重（以 `username` 為 key）
   - 補 `account_link`（若缺，補 `https://www.instagram.com/{username}/`）
3. **跳過 scrolling**
   - 不再開 following dialog / 不再執行 `extract_following_list`
   - `scroll_stop_reason` 會標記成 `resume_from_artifact`
4. **只補跑未完成的帳號**
   - `done` 定義：`page_analyzed_at` 存在且無 `page_analysis_error`，或有任何一個 `*_count_text` 已填
   - `needs_visit` 定義：
     - 若 `page_analysis_error` 存在：是否重跑由 `IG_RESUME_REVISIT_ERRORS` 控制（預設重跑）
     - 否則若 `done`：跳過
     - 其餘：執行 `analyze_account_page`
5. **進度呈現**
   - 初始化 visiting_pages 時，會先寫入 progress：
     - `resume_from_artifact=true`
     - `resume_artifact_id`
     - `resume_done_count`
     - `page_total=len(accounts)`
     - `page_index=done_count`（表示已完成的基數）
   - 每次分析前仍會更新 `page_index=i`（i 為 accounts 的原 index），確保 UI 仍能對應到原列表位置

---

## 參數與環境變數

### 功能開關

- **`IG_RESUME_VISIT_PAGES`**
  - `1`（預設）：啟用續跑
  - `0`：關閉續跑（每次都重新 scrolling + visiting）

### 續跑門檻

- **`IG_RESUME_MIN_ACCOUNTS`**
  - 預設 `30`
  - 避免從極小/明顯不完整的名單（例如 12）直接進入 visiting_pages

### 失敗重跑

- **`IG_RESUME_REVISIT_ERRORS`**
  - `1`（預設）：曾經 `page_analysis_error` 的帳號會在續跑時再嘗試一次
  - `0`：跳過錯誤頁（只跑完全沒分析過的）

---

## 失敗模式與預期行為

### 1) 前一輪 scrolling 不完整（例：198/3332）

續跑 visiting_pages 仍可運作（因為名單已存在且 >= min），但只能分析「已拿到的 198」。
若你的最高優先是「名單要完整」，請先跑一輪 `visit_account_pages=false` 專注把名單拉滿，再開啟續跑 visiting_pages。

### 2) 前一輪 visiting_pages 卡死 / runner reaper 標 failed

- 新任務啟動後會從 progress artifact 讀回名單
- 已完成的 pages 會被跳過（或僅重跑錯誤頁）
- 因為這是新 execution，所以不需要修改舊任務狀態，也不需要砍舊任務

### 3) 名單來源不匹配（不同 target 或不同 profile）

為避免拿錯登入帳號的名單，續跑只會匹配：

- 同 `target_username`
- 同 `user_data_dir`（`source_profile_ref`）

---

## 實作位置（Code Map）

- **續跑入口**：`capabilities/ig/tools/following_analyzer/runner.py`
  - `_load_resume_accounts()`：選取並載入 progress artifact 的 accounts
  - `_normalize_accounts()`：去重 + 補 account_link
  - visiting loop 中 `_needs_visit()`：判斷是否需要分析此帳號頁

---

## 驗證方式（你應該怎麼驗證它真的能續跑）

1. **先跑一輪拿名單**
   - `visit_account_pages=true`（或 false 也可，只要 progress artifact 有 accounts）
   - 等到 `targets` 有一批（例如 200+）
2. **中途故障**（例如 runner 被重啟 / reaper 標 stale / 或你手動停止）
3. **再開一輪同目標同 profile**
   - 同 `target_username`
   - 同 `user_data_dir`
   - `visit_account_pages=true`
4. 觀察 progress artifact：
   - `resume_from_artifact=true`
   - `resume_artifact_id` 有值
   - `page_total` == 名單長度
   - 已分析的帳號會被 skip（頁數會快速前進或略過）

