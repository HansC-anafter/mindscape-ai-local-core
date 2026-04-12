## 事件檢討報告：`ig_analyze_following` 執行進度顯示誤導（2026-01-19）

### 摘要
本次事件中，使用者的執行（execution id `291887c6-c6f4-4612-85a5-f8d80a8416f0`）在 UI 仍長時間顯示：

- stage `scrolling`
- iter `18`
- targets `75`
- bottom `yes`

造成使用者判斷「卡住 / 沒有順利執行完」。實際上，UI 顯示的是「最後一次寫入的 progress artifact」，但 progress 在後續階段沒有更新，導致 UI 呈現過期狀態。

### 影響
- **使用者體驗**：使用者在長時間等待後仍看到相同 stage，合理推斷系統卡死或無進展。
- **可觀測性不足**：僅有 `running` 狀態不足以證明工作仍在前進；缺少可追蹤的「最後更新時間」與「是否進度停更」訊號。
- **信任受損**：在沒有以「最後更新時間」驗證的情況下對外回報「正在跑」，被視為不可靠。

### 根因（Root Cause）
#### 1) 進度資料模型不完整
`ig_analyze_following` 的 progress artifact 只在「following list scrolling」階段持續更新；當流程進入「逐頁拜訪帳號（visit_account_pages）」後，沒有持續寫入 progress（例如 `visiting_pages`、`current_account`、`page_index/page_total`），因此 UI 無法呈現後續階段進度。

#### 2) UI 依賴單一訊號（progress artifact）但未標示「是否過期」
Accounts 的狀態列以 progress artifact 的 `stage/iter/...` 作為主顯示，但在 progress 長時間不變時，UI 仍呈現「像是現況」的資訊，未提示使用者「這可能是過期資料」。

#### 3) 回報流程缺少「最小可驗證證據」
在對外回報「仍在跑」之前，沒有先用兩個關鍵檢查交叉驗證：
- progress artifact 的 `updated_at` 是否持續更新
- 後端是否仍有產生活動（例如 heartbeat / 階段更新）

### 修正（Corrective Actions）
#### A) 後端：補齊 visit_account_pages 的 progress 更新（僅對新 run 生效）
在逐頁拜訪帳號前與每次拜訪前寫入：
- stage `visiting_pages`
- page_index / page_total
- current_account
- total_accounts

這讓 UI 不再停留在 `scrolling`，而是能跟著流程顯示當前階段與進度。

#### A-2) 後端：確保 progress artifact 一定能對上 execution（僅對新 run 生效）
部分 runtime 只會提供 `execution_id` 而不提供 `trace_id`，導致工具層不會啟用 progress artifact（`workspace_id && trace_id` 才會初始化 artifacts store）。

已落地修正：
- 若 `trace_id` 缺省，改用 `execution_id` 作為 trace fallback，避免「任務在跑但 UI 永遠 stale」。

#### A-3) 後端：避免工具卡死導致 progress 停更（僅對新 run 生效）
- 在 account page 分析加 hard timeout（預設 90s，可由 `IG_ACCOUNT_PAGE_TIMEOUT_SEC` 調整）
- 並在失敗時也寫入一筆 `visiting_pages` progress（含 `error_type/error_message`），避免 UI 無限停在舊狀態

#### B) 前端：顯示 last update 並標示 stale（對舊 run 也生效）
Accounts 狀態列新增：
- **last update 本地時間**
- **(Xm ago)**
- **stale 標記與視覺提示**（進度超過門檻未更新時）

此改動不會讓舊 execution 產生新的 progress，但能讓使用者明確辨識「目前顯示的進度是過期的」。

### 立即補救（Immediate Mitigation）
- 對於已啟動且 progress 已停更的舊 execution，UI 會以 **stale** 警示避免誤導。
- 若需要完整可視進度，必須以已修正版本重新執行一次（舊 execution 不會 retroactively 補寫 progress）。

### 預防措施（Preventive Actions）
- **制訂 UI 顯示規則**：任何「running 但 progress 未更新」必須以 stale 呈現，不允許以過期 stage 當作現況。
- **新增執行 heartbeat**：長流程工具應定期更新 progress（即使沒有新增 accounts，也要更新 stage/heartbeat timestamp）。
- **建立回報準則**：對外回報「仍在跑」必須至少提供 `last_update`（或 heartbeat）與時間差，避免只用 `running` 狀態推斷。

### 相關落地修正（同日）
#### Runner：避免 heartbeat/鎖續租被主流程卡死拖垮
- Runner 的 heartbeat/lock renew 改為背景 thread，避免 Playwright/執行器卡住時 heartbeat 停更而被 reaper 誤判。
- IG profile lock 拿到後會清掉舊的 `runner_skip_reason/owner`，避免 UI 顯示殘留 skip 狀態。

