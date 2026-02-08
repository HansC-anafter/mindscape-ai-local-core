---
playbook_code: annual_track_cohort
version: 1.0.0
capability_code: walkto_lab
name: Annual Track 共學
description: |
  訂閱 Annual Track（$29/月 或 $290/年），加入共學群組，被陪伴著把一種世界觀活進生活。
  包含每週共學 Session、回寫卡、月里程碑，以及最終 Personal Dataset 交付。
tags:
  - walkto
  - subscription
  - cohort
  - annual-track
  - co-learning

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - walkto_record_walk_session
  - walkto_writeback_universe
  - walkto_generate_dataset
  - cloud_capability.call

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🎯
---

# Annual Track 共學 - SOP

## 目標

讓使用者訂閱並參與 Annual Track（$29/月 或 $290/年），提供：

1. **每週共學 Session**：60-90 分鐘的探索與收束 Session
2. **每週回寫卡**：每次 Session 後的個人偏好與規則提取
3. **每週資料包增量**：個人資料包每週成長
4. **月里程碑**：完成度檢查點與進度回顧
5. **最終 Personal Dataset**：12 週後完整的可攜生活資料包

**核心價值**：
- 被陪伴著把一種世界觀活進生活
- 把不確定的過程治理成可完成的練習
- 帶走屬於自己的方法與規則

**標準結構**：
- **週節奏**：共學 Session + 回寫卡 + 資料包增量
- **月里程碑**：完成度檢查點
- **最終交付**：Personal Dataset（可攜生活資料包）

## 執行步驟

### Phase 0: 訂閱與加入共學群組

**執行順序**：
1. Step 0.0: 識別目標 Track
2. Step 0.1: 檢查現有訂閱狀態
3. Step 0.2: 建立或啟用 Annual Track 訂閱
4. Step 0.3: 加入或建立 Cohort

#### Step 0.0: 識別目標 Track

詢問使用者：
- 你想加入哪個 Annual Track？
- 你有特定的 track_id 嗎？
- 或者你想瀏覽可用的 Tracks？

**Track 類型**：
- 年度讀書（例如：資治通鑑、費曼、行為經濟學）
- 年度身體練習（例如：RYT 200）
- 年度心智練習（例如：正念 100 小時）
- 年度文化實踐（例如：城市/咖啡/博物館探索）

**輸出**：
- `track_id`: 目標 Track 識別碼
- `track_name`: Track 名稱
- `track_type`: Track 類型
- `lens_id`: 關聯的 Lens 識別碼

#### Step 0.1: 檢查現有訂閱狀態

檢查使用者是否已有有效的 Annual Track 訂閱：
- 查詢訂閱服務的 user_id 和 tier="annual_track"
- 檢查訂閱是否有效且未過期
- 檢查訂閱是否關聯到某個 track

**輸出**：
- `has_active_subscription`: 布林值
- `existing_subscription`: 訂閱物件（如存在）
- `subscription_status`: "active" | "cancelled" | "expired" | "none"
- `associated_track_id`: 關聯的 track ID（如存在）

#### Step 0.2: 建立或啟用 Annual Track 訂閱

如果沒有有效訂閱：
1. 透過訂閱服務建立新訂閱
2. 設定 tier 為 "annual_track"
3. 設定到期日為 30 天後（月付）或 365 天後（年付）
4. 關聯訂閱到 track_id
5. 處理付款（如需要）

如果訂閱存在但已過期：
1. 續訂訂閱
2. 更新到期日
3. 處理付款（如需要）

如果訂閱有效：
1. 確認訂閱有效
2. 進入 Step 0.3

**輸出**：
- `subscription_id`: 訂閱識別碼
- `subscription_status`: "active"
- `expires_at`: 到期時間戳記
- `track_id`: 關聯的 track ID

#### Step 0.3: 加入或建立 Cohort

如果此 track 已有 cohort：
1. 檢查 cohort 容量
2. 將使用者加入 cohort
3. 設定使用者的開始日期
4. 初始化使用者的每週進度追蹤

如果 cohort 不存在：
1. 為此 track 建立新 cohort
2. 設定 cohort 容量（例如：10-20 位參與者）
3. 將使用者加入為第一位參與者
4. 設定 cohort 開始日期
5. 初始化 cohort 排程

**輸出**：
- `cohort_id`: Cohort 識別碼
- `cohort_name`: Cohort 名稱
- `participant_count`: 當前參與者數量
- `user_start_date`: 使用者在 cohort 中的開始日期
- `cohort_schedule`: 每週 Session 排程

### Phase 1: 週節奏管理

**執行順序**：
1. Step 1.0: 檢查當前週狀態
2. Step 1.1: 參加或回顧每週 Session
3. Step 1.2: 完成回寫卡
4. Step 1.3: 更新個人資料包增量

#### Step 1.0: 檢查當前週狀態

查詢使用者的當前週狀態：
- 取得當前週數（1-12）
- 檢查每週 Session 是否已排程
- 檢查回寫卡是否已完成
- 檢查資料包增量是否已更新

**輸出**：
- `current_week`: 當前週數（1-12）
- `session_status`: "scheduled" | "completed" | "missed" | "none"
- `writeback_status`: "pending" | "completed" | "none"
- `dataset_status`: "pending" | "updated" | "none"

#### Step 1.1: 參加或回顧每週 Session

如果 Session 已排程：
1. 提供 Session 詳情（時間、地點、主題）
2. 如果 Session 即將開始，發送提醒
3. 引導使用者參加 Session
4. Session 後，記錄 Session 資料

如果 Session 已完成：
1. 顯示 Session 摘要
2. 顯示 Session 素材（照片、筆記、觀察）
3. 引導使用者完成回寫卡

如果 Session 錯過：
1. 告知使用者錯過的 Session
2. 提供補課選項（如有）
3. 更新進度追蹤

**Session 結構**（60-90 分鐘）：
- **探索階段**（30-45 分鐘）：引導觀察、提問、互動
- **收束階段**（20-30 分鐘）：總結發現、提取洞察
- **收尾**（10-15 分鐘）：提出下週任務、設定期望

**輸出**：
- `session_id`: Session 識別碼
- `session_date`: Session 日期
- `session_summary`: Session 摘要
- `session_artifacts`: Session 素材（照片、筆記、觀察）
- `lens_notes`: 從 Session 提取的 Lens notes

#### Step 1.2: 完成回寫卡

每次 Session 後，引導使用者完成回寫卡：
1. 收集使用者偏好（使用者喜歡/不喜歡什麼）
2. 提取狀態更新（使用者何時感受到什麼）
3. 生成個人規則（基於 Session 的 3-7 條規則）
4. 收集信任證據（使用者何時感到被理解）

**回寫卡內容**：
- **偏好**：價格敏感度、美學偏好、氛圍偏好
- **狀態更新**：狀態地圖更新（例如："quiet" → "cozy_cafe"）
- **規則**：個人選擇規則（例如："工作時避免吵鬧的地方"）
- **信任證據**：使用者感到被理解的時刻

**輸出**：
- `writeback_card_id`: 回寫卡識別碼
- `preferences`: 使用者偏好物件
- `rules`: 個人規則列表（3-7 條規則）
- `state_updates`: 狀態地圖更新
- `trust_evidence`: 信任證據列表

#### Step 1.3: 更新個人資料包增量

回寫卡完成後，更新個人資料包：
1. 將新偏好加入資料包
2. 將新規則加入資料包
3. 更新狀態地圖
4. 將 Session 素材加入資料包
5. 更新路線模板（如適用）

**資料包增量內容**：
- 新偏好
- 新規則
- 更新的狀態地圖
- Session 素材
- 路線模板（如適用）

**輸出**：
- `dataset_increment_id`: 資料包增量識別碼
- `updated_dataset`: 更新的資料包物件
- `increment_summary`: 本週增量摘要

### Phase 2: 月里程碑檢查

**執行順序**：
1. Step 2.0: 檢查里程碑是否到期
2. Step 2.1: 生成里程碑報告
3. Step 2.2: 回顧進度並提供指引

#### Step 2.0: 檢查里程碑是否到期

檢查月里程碑是否到期：
- 計算當前月份（1-12）
- 檢查當前月份是否有里程碑報告
- 如果沒有，檢查是否該生成（每月第一天）

**輸出**：
- `milestone_due`: 布林值
- `current_month`: 當前月份（1-12）
- `milestone_date`: 里程碑日期
- `next_milestone_date`: 下次里程碑日期

#### Step 2.1: 生成里程碑報告

生成月里程碑報告：
1. 彙總過去一個月的所有每週 Session
2. 計算完成率
3. 提取關鍵學習與模式
4. 識別進度與差距
5. 生成建議

**里程碑報告內容**：
- **完成狀態**：使用者完成了什麼
- **學會的規則**：使用者現在使用哪些規則（3-7 條規則）
- **下一步**：使用者應該如何進行
- **進度指標**：完成率、參與率等

**輸出**：
- `milestone_report_id`: 里程碑報告識別碼
- `completion_status`: 完成狀態物件
- `rules_learned`: 學會的規則列表
- `next_steps`: 下一步列表
- `progress_metrics`: 進度指標物件

#### Step 2.2: 回顧進度並提供指引

向使用者呈現里程碑報告：
1. 顯示完成狀態
2. 突出學會的規則
3. 提供下一步指引
4. 處理任何疑慮或差距
5. 鼓勵持續參與

**指引格式**：
```
月里程碑 - [Track 名稱]
月份：[月份]

你完成了什麼：
- [完成項目 1]
- [完成項目 2]
...

你現在使用的規則：
1. [規則 1]
2. [規則 2]
...

如何進行：
- [下一步 1]
- [下一步 2]
...
```

**驗收標準**：
- ✅ 里程碑報告清晰呈現
- ✅ 完成狀態準確
- ✅ 學會的規則突出顯示
- ✅ 下一步可執行

### Phase 3: 最終 Personal Dataset 交付

**執行順序**：
1. Step 3.0: 檢查 Track 是否完成
2. Step 3.1: 生成最終 Personal Dataset
3. Step 3.2: 以請求格式導出資料包
4. Step 3.3: 交付資料包給使用者

#### Step 3.0: 檢查 Track 是否完成

檢查使用者是否已完成 12 週：
- 計算總完成週數
- 檢查所有必要 Session 是否完成
- 檢查所有回寫卡是否完成
- 驗證資料包是否完整

**輸出**：
- `track_completed`: 布林值
- `weeks_completed`: 總完成週數（1-12）
- `completion_rate`: 完成率百分比
- `dataset_complete`: 布林值

#### Step 3.1: 生成最終 Personal Dataset

12 週後生成最終 Personal Dataset：
1. 收集所有 Session 的所有偏好
2. 彙總所有規則（3-7 條最終規則）
3. 編譯完整狀態地圖（至少 5 個狀態）
4. 收集所有路線模板（如適用）
5. 生成下一階段行動指引

**Personal Dataset 內容**（最低要求）：
- **狀態與偏好地圖**：完整的狀態地圖與偏好
- **選擇規則**：3-7 條個人選擇規則
- **練習模板**：練習或路線模板（如適用至少 1 個）
- **下一階段行動指引**：下一階段指引

**輸出**：
- `dataset_id`: 資料包識別碼
- `dataset`: Personal Dataset 物件
- `dataset_completeness`: 資料包完整度檢查結果

#### Step 3.2: 以請求格式導出資料包

以使用者請求的格式導出資料包：
- **JSON**：結構化 JSON 格式
- **Markdown**：人類可讀的 Markdown 格式
- **Notion**：Notion 資料庫格式

**導出選項**：
- 完整資料包導出
- 增量導出（僅自上次導出後的新資料）
- 自訂格式導出

**輸出**：
- `export_format`: 導出格式（json/markdown/notion）
- `export_file`: 導出檔案路徑或 URL
- `export_timestamp`: 導出時間戳記

#### Step 3.3: 交付資料包給使用者

將資料包交付給使用者：
1. 提供下載連結或檔案
2. 顯示資料包摘要
3. 說明如何使用資料包
4. 提供下一步指引

**交付格式**：
```
Personal Dataset - [Track 名稱]
完成日期：[日期]

你的狀態與偏好地圖：
[狀態地圖內容]

你的選擇規則：
1. [規則 1]
2. [規則 2]
...

你的練習模板：
[模板內容]

下一階段行動指引：
[行動指引內容]

下載：[下載連結]
```

**驗收標準**：
- ✅ 資料包完整（所有必要欄位）
- ✅ 資料包包含至少 3 條規則
- ✅ 資料包包含至少 5 個狀態
- ✅ 資料包包含至少 1 個路線模板（如適用）
- ✅ 資料包以請求格式交付

### Phase 4: 共學群組管理

**執行順序**：
1. Step 4.0: 查看群組狀態
2. Step 4.1: 管理錯過的 Session
3. Step 4.2: 更新訂閱或取消

#### Step 4.0: 查看群組狀態

查看當前群組狀態：
- 顯示群組參與者
- 顯示群組排程
- 顯示群組進度
- 顯示即將到來的 Session

**輸出**：
- `cohort_status`: 群組狀態物件
- `participants`: 參與者列表
- `upcoming_sessions`: 即將到來的 Session 列表
- `cohort_progress`: 群組進度指標

#### Step 4.1: 管理錯過的 Session

如果使用者錯過 Session：
1. 識別錯過的 Session
2. 提供補課選項（如有）
3. 更新進度追蹤
4. 確保回寫卡仍可完成

**補課選項**：
- 提前參加下次 Session
- 獨立完成 Session
- 觀看 Session 錄影（如有）
- 排程補課 Session

**輸出**：
- `missed_sessions`: 錯過的 Session 列表
- `makeup_options`: 補課選項列表
- `progress_updated`: 布林值

#### Step 4.2: 更新訂閱或取消

如果使用者想更新訂閱：
1. 處理付款（如需要）
2. 更新到期日
3. 確認續訂

如果使用者想取消：
1. 更新訂閱狀態為 "cancelled"
2. 確認取消
3. 告知使用者到期前仍可存取
4. 提供資料包導出選項（如適用）

**輸出**：
- `action_taken`: "renewed" | "cancelled" | "none"
- `new_expiration_date`: 更新的到期日（如續訂）

## 驗收標準

### 訂閱與加入群組
- ✅ 使用者可以訂閱 Annual Track
- ✅ 訂閱以正確 tier（"annual_track"）建立
- ✅ 使用者可以加入或建立 cohort
- ✅ 付款已處理（如需要）
- ✅ 訂閱到期日設定正確（30 天或 365 天）

### 週節奏
- ✅ 使用者可以參加每週 Session
- ✅ 使用者可以完成回寫卡
- ✅ 使用者的資料包每週更新
- ✅ Session 素材已收集

### 月里程碑
- ✅ 月里程碑報告已生成
- ✅ 完成狀態準確
- ✅ 學會的規則突出顯示
- ✅ 下一步可執行

### 最終資料包交付
- ✅ 12 週後生成最終 Personal Dataset
- ✅ 資料包包含所有必要欄位
- ✅ 資料包包含至少 3 條規則
- ✅ 資料包包含至少 5 個狀態
- ✅ 資料包以請求格式交付

### 群組管理
- ✅ 使用者可以查看群組狀態
- ✅ 使用者可以管理錯過的 Session
- ✅ 使用者可以更新或取消訂閱

## 錯誤處理

### 訂閱錯誤
- 如果訂閱建立失敗：告知使用者並重試
- 如果付款失敗：告知使用者並提供替代付款方式
- 如果訂閱已過期：提示使用者續訂

### Session 錯誤
- 如果 Session 錯過：提供補課選項
- 如果 Session 錄影失敗：重試並告知使用者
- 如果 Session 資料不完整：提示使用者完成

### 回寫錯誤
- 如果回寫卡不完整：提示使用者完成
- 如果回寫生成失敗：重試並告知使用者

### 資料包錯誤
- 如果資料包生成失敗：重試並告知使用者
- 如果資料包不完整：檢查完整度並提示使用者
- 如果導出失敗：重試並告知使用者

## 注意事項

- Annual Track 是高級訂閱（$29/月 或 $290/年）
- 重點在於被陪伴著把世界觀活進生活
- 週節奏確保持續進度
- 月里程碑提供檢查點
- 最終 Personal Dataset 是關鍵交付物和續訂理由
- 完成率目標：≥70%













