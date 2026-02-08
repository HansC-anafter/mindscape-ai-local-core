---
playbook_code: walk_session
version: 1.0.0
capability_code: walkto_lab
name: 散步 Session
description: |
  參與單場散步 Session，包含探索、收束與回寫。
  遵循節奏：約定 → 探索 → 收束 → 回寫。
tags:
  - walkto
  - walk-session
  - co-learning
  - exploration

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
  - cloud_capability.call

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🚶
---

# 散步 Session - SOP

## 目標

讓使用者參與單場散步 Session，遵循以下節奏：

1. **約定階段**：設定期望、確認主題、理解視角
2. **探索階段**：觀察、提問、與環境和參與者互動
3. **收束階段**：總結發現、提取洞察、識別模式
4. **回寫階段**：提供偏好、狀態更新、生成個人規則

**核心價值**：
- 將單場散步轉化為結構化學習體驗
- 從實地觀察中提取可執行的洞察
- 基於真實經驗建立個人規則

**Session 結構**（60-90 分鐘）：
- **約定**（10-15 分鐘）：設定期望並確認理解
- **探索**（30-45 分鐘）：引導觀察與互動
- **收束**（20-30 分鐘）：總結並提取洞察
- **回寫**（10-15 分鐘）：提供回饋並生成規則

## 執行步驟

### Phase 0: 準備

**執行順序**：
1. Step 0.0: 識別 Session 情境
2. Step 0.1: 取得 Lens Card 與主題
3. Step 0.2: 確認參與準備

#### Step 0.0: 識別 Session 情境

取得 Session 資訊：
- `session_id`: Session 識別碼（如加入現有 Session）
- `lens_id`: 關聯的 Lens 識別碼
- `track_id`: 關聯的 Track 識別碼（如為 Annual Track 的一部分）
- `cohort_id`: 關聯的 Cohort 識別碼（如為群組的一部分）

**輸出**：
- `session_id`: Session 識別碼
- `lens_id`: Lens 識別碼
- `session_context`: Session 情境（獨立/群組/軌道）

#### Step 0.1: 取得 Lens Card 與主題

取得 Lens Card 與 Session 主題：
- 從 lens_id 取得 Lens Card
- 取得 Session 主題與目標
- 理解視角與判斷標準

**輸出**：
- `lens_card`: Lens Card 物件
- `topic`: Session 主題
- `judgment_criteria`: 判斷標準列表
- `perspective_model`: 視角模型

#### Step 0.2: 確認參與準備

確認使用者準備參與：
- 檢查使用者是否有必要素材（如需要）
- 確認使用者理解 Session 結構
- 設定使用者的初始狀態與期望

**輸出**：
- `user_ready`: 布林值
- `initial_state`: 使用者的初始狀態
- `user_expectations`: 使用者對 Session 的期望

### Phase 1: 約定

**執行順序**：
1. Step 1.0: 理解 Session 目標
2. Step 1.1: 確認視角
3. Step 1.2: 設定個人期望
4. Step 1.3: 同意 Session 結構

#### Step 1.0: 理解 Session 目標

向使用者呈現 Session 目標：
- 今天我們要探索什麼？
- 我們將使用什麼視角？
- 預期成果是什麼？

**目標格式**：
```
Session 目標：
- 主題：[主題]
- 視角：[視角]
- 預期成果：
  1. [成果 1]
  2. [成果 2]
  3. [成果 3]
```

**輸出**：
- `session_objectives`: Session 目標物件
- `user_understands`: 布林值（使用者確認理解）

#### Step 1.1: 確認視角

向使用者呈現視角：
- 顯示判斷標準
- 解釋視角模型
- 說明視角幫助我們看到什麼

**視角格式**：
```
視角：[Lens 名稱]

這個視角幫助我們看到：
- [視角 1]
- [視角 2]
- [視角 3]

判斷標準：
1. [標準 1]
2. [標準 2]
...
```

**輸出**：
- `lens_perspective_confirmed`: 布林值
- `user_questions`: 使用者對視角的問題（如有）

#### Step 1.2: 設定個人期望

詢問使用者的期望：
- 你今天想探索什麼？
- 你希望什麼樣的體驗？（安靜/社交/探索/放鬆）
- 你對這個 Session 的個人目標是什麼？

**輸出**：
- `user_expectations`: 使用者的期望物件
- `desired_experience_type`: 期望的體驗類型
- `personal_goals`: 個人目標列表

#### Step 1.3: 同意 Session 結構

與使用者確認 Session 結構：
- 解釋約定 → 探索 → 收束 → 回寫節奏
- 設定每個階段的時間期望
- 確認使用者同意參與

**Session 結構格式**：
```
Session 結構：
1. 約定（10-15 分鐘）：設定期望並確認理解
2. 探索（30-45 分鐘）：觀察、提問、互動
3. 收束（20-30 分鐘）：總結發現並提取洞察
4. 回寫（10-15 分鐘）：提供回饋並生成規則

總時長：60-90 分鐘
```

**輸出**：
- `session_structure_confirmed`: 布林值
- `user_agrees`: 布林值

### Phase 2: 探索

**執行順序**：
1. Step 2.0: 開始探索
2. Step 2.1: 引導觀察
3. Step 2.2: 促進互動
4. Step 2.3: 收集觀察

#### Step 2.0: 開始探索

開始探索階段：
- 引導使用者開始觀察
- 基於視角提供觀察提示
- 鼓勵積極參與

**探索提示**：
- "你注意到 [方面] 的什麼？"
- "這與視角有什麼關係？"
- "這對你提出了什麼問題？"
- "這裡什麼對你來說很重要？"

**輸出**：
- `exploration_started`: 布林值
- `initial_observations`: 初始觀察列表

#### Step 2.1: 引導觀察

引導使用者進行結構化觀察：
- 基於視角聚焦特定方面
- 使用判斷標準作為觀察指南
- 鼓勵詳細、具體的觀察

**觀察指引**：
```
觀察重點領域：
1. [重點領域 1] - 基於視角
2. [重點領域 2] - 基於視角
3. [重點領域 3] - 基於視角

觀察提示：
- 你看到/聽到/感受到什麼？
- 這如何符合或不同於視角？
- 什麼對你來說很突出？
```

**輸出**：
- `observations`: 觀察列表
- `observation_details`: 詳細觀察筆記

#### Step 2.2: 促進互動

促進與環境和參與者的互動：
- 鼓勵提問與討論
- 基於視角引導互動
- 收集互動素材（照片、筆記等）

**互動指引**：
- 基於視角提問
- 與他人分享觀察（如在群組中）
- 積極與環境互動
- 記錄有趣的時刻

**輸出**：
- `interactions`: 互動列表
- `interaction_artifacts`: 收集的素材（照片、筆記等）
- `questions_asked`: 提出的問題列表

#### Step 2.3: 收集觀察

收集探索階段的所有觀察：
- 按主題組織觀察
- 將觀察連結到視角
- 識別模式或有趣點

**觀察收集格式**：
```
收集的觀察：
1. [觀察 1] - 與 [視角方面] 相關
2. [觀察 2] - 與 [視角方面] 相關
3. [觀察 3] - 與 [視角方面] 相關
...

識別的模式：
- [模式 1]
- [模式 2]
...
```

**輸出**：
- `all_observations`: 完整觀察列表
- `patterns_identified`: 識別的模式列表
- `artifacts_collected`: 所有收集的素材

### Phase 3: 收束

**執行順序**：
1. Step 3.0: 總結發現
2. Step 3.1: 提取洞察
3. Step 3.2: 識別關鍵學習
4. Step 3.3: 準備回寫

#### Step 3.0: 總結發現

總結探索階段發現的內容：
- 將觀察組織成主題
- 突出關鍵發現
- 將發現連結到視角

**總結格式**：
```
Session 總結：

關鍵發現：
1. [發現 1] - [簡短描述]
2. [發現 2] - [簡短描述]
3. [發現 3] - [簡短描述]

主題：
- [主題 1]：[相關發現]
- [主題 2]：[相關發現]
...
```

**輸出**：
- `session_summary`: Session 總結物件
- `key_findings`: 關鍵發現列表
- `themes`: 識別的主題

#### Step 3.1: 提取洞察

從發現中提取可執行的洞察：
- 我們學到了什麼？
- 出現了什麼模式？
- 哪些問題得到回答或提出？

**洞察格式**：
```
提取的洞察：

我們學到的：
- [洞察 1]
- [洞察 2]
- [洞察 3]

出現的模式：
- [模式 1]
- [模式 2]

問題：
- 已回答：[問題 1]
- 已提出：[問題 2]
```

**輸出**：
- `insights`: 洞察列表
- `patterns`: 識別的模式
- `questions`: 已回答和提出的問題

#### Step 3.2: 識別關鍵學習

識別最重要的學習：
- 關鍵要點是什麼？
- 使用者會記住這個 Session 的什麼？
- 什麼可以應用到未來？

**關鍵學習格式**：
```
關鍵學習：

1. [學習 1] - [為什麼重要]
2. [學習 2] - [為什麼重要]
3. [學習 3] - [為什麼重要]

應用：
- [如何應用學習 1]
- [如何應用學習 2]
...
```

**輸出**：
- `key_learnings`: 關鍵學習列表
- `applications`: 應用列表

#### Step 3.3: 準備回寫

為使用者準備回寫階段：
- 解釋回寫涉及什麼
- 預覽將收集的資訊
- 設定期望規則生成

**回寫預覽**：
```
下一步：回寫階段

我們將收集：
- 你的偏好（你喜歡/不喜歡什麼）
- 狀態更新（你的感受）
- 基於今天的經驗生成個人規則

這有助於建立你的個人資料包。
```

**輸出**：
- `writeback_prepared`: 布林值
- `user_ready_for_writeback`: 布林值

### Phase 4: 回寫

**執行順序**：
1. Step 4.0: 收集偏好
2. Step 4.1: 更新狀態
3. Step 4.2: 生成規則
4. Step 4.3: 記錄 Session

#### Step 4.0: 收集偏好

從 Session 收集使用者偏好：
- 使用者喜歡/不喜歡什麼？
- 價格敏感度觀察
- 美學偏好
- 氛圍偏好

**偏好收集**：
```
偏好收集：

你喜歡的：
- [偏好 1]
- [偏好 2]
...

你不喜歡的：
- [不喜歡 1]
- [不喜歡 2]
...

價格敏感度：[低/中/高]
美學偏好：[偏好]
氛圍偏好：[偏好]
```

**輸出**：
- `preferences`: 偏好物件
- `likes`: 喜歡列表
- `dislikes`: 不喜歡列表

#### Step 4.1: 更新狀態

基於 Session 更新使用者的狀態地圖：
- 使用者在 Session 期間的感受如何？
- 經歷了哪些狀態？
- 更新狀態轉換

**狀態更新格式**：
```
狀態更新：

經歷的狀態：
- [狀態 1]：[何時/為什麼]
- [狀態 2]：[何時/為什麼]
...

狀態轉換：
- [狀態 A] → [狀態 B]：[觸發]
- [狀態 B] → [狀態 C]：[觸發]
...
```

**輸出**：
- `state_updates`: 狀態更新物件
- `states_experienced`: 經歷的狀態列表
- `state_transitions`: 狀態轉換列表

#### Step 4.2: 生成規則

基於 Session 生成個人規則：
- 從觀察和偏好中提取規則
- 生成 3-7 條可執行的規則
- 確保規則具體且可應用

**規則生成格式**：
```
生成的個人規則：

1. [規則 1] - [情境/何時應用]
2. [規則 2] - [情境/何時應用]
3. [規則 3] - [情境/何時應用]
...

規則來源：
- 規則 1：基於 [觀察/偏好]
- 規則 2：基於 [觀察/偏好]
...
```

**輸出**：
- `rules`: 規則列表（3-7 條規則）
- `rule_sources`: 規則來源列表
- `rules_validated`: 布林值

#### Step 4.3: 記錄 Session

記錄完整的 Session 資料：
- 儲存 Session 總結
- 儲存觀察與素材
- 儲存偏好、狀態與規則
- 連結到視角與軌道（如適用）

**Session 記錄格式**：
```
Session 已記錄：

Session ID：[session_id]
日期：[日期]
主題：[主題]
視角：[視角名稱]

總結：[session_summary]
觀察：[observations_count]
素材：[artifacts_count]
生成的規則：[rules_count]

狀態：完成
```

**輸出**：
- `session_recorded`: 布林值
- `session_id`: Session 識別碼
- `writeback_complete`: 布林值

## 驗收標準

### 約定階段
- ✅ 使用者理解 Session 目標
- ✅ 使用者確認視角
- ✅ 使用者設定個人期望
- ✅ 使用者同意 Session 結構

### 探索階段
- ✅ 使用者積極觀察
- ✅ 使用者提問
- ✅ 使用者與環境/參與者互動
- ✅ 觀察已收集

### 收束階段
- ✅ 發現已總結
- ✅ 洞察已提取
- ✅ 關鍵學習已識別
- ✅ 使用者已準備回寫

### 回寫階段
- ✅ 偏好已收集
- ✅ 狀態已更新
- ✅ 規則已生成（3-7 條規則）
- ✅ Session 已記錄

## 錯誤處理

### 準備錯誤
- 如果 Session 情境缺失：提示使用者提供 session_id 或建立新 Session
- 如果 Lens Card 找不到：告知使用者並提供替代選項

### 約定錯誤
- 如果使用者不理解目標：重新解釋並確認理解
- 如果使用者不同意結構：調整結構或結束 Session

### 探索錯誤
- 如果探索停滯：提供提示與指引
- 如果觀察稀少：鼓勵更詳細的觀察

### 收束錯誤
- 如果發現不清楚：幫助使用者澄清與組織
- 如果洞察薄弱：引導使用者深入反思

### 回寫錯誤
- 如果偏好不完整：提示使用者提供更多細節
- 如果無法生成規則：使用預設規則或提示更多輸入
- 如果 Session 記錄失敗：重試並告知使用者

## 注意事項

- 散步 Session 是獨立 Session（不一定屬於某個軌道）
- 重點在於結構化探索與學習
- 回寫階段對建立個人資料包至關重要
- 生成的規則應該具體且可執行
- Session 可以是 Annual Track 的一部分或獨立進行













