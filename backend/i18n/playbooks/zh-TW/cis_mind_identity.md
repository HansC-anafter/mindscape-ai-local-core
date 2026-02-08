# 🧠 MI 品牌心智

> **AI 負責的是「探索可能性」，你和設計師負責的是「決定你要成為誰」。**

## 目標

建立品牌的核心心智模型，包括：
- 品牌定位與價值主張
- 品牌世界觀
- 品牌紅線（永遠不做的事）
- 品牌人格與語氣

## 責任分配

| 步驟 | 責任 | AI 角色 | 人類角色 |
|------|------|---------|----------|
| 世界觀探索 | 🟡 AI提案 | 產生 3-5 套候選世界線 | 品牌方選擇，設計師翻譯成視覺 |
| 價值主張 | 🟡 AI提案 | 分析競品，提出差異化建議 | 品牌方確認核心價值 |
| **品牌紅線** | 🔴 Only Human | 列出可能的「不做清單」 | **品牌方親自決定** |
| 品牌人格 | 🟡 AI提案 | 生成人格特質選項 | 品牌方選擇，設計師轉化 |

---

## Step 1: 收集品牌背景

首先，我需要了解品牌的基礎信息。

### 方式 A：提供已有文檔（推薦）

如果你已經有品牌相關的文檔（訪談稿、品牌簡報、提案等），可以直接提供：

1. **在對話中貼上文檔內容**
   - 可以直接貼上完整的文檔內容
   - 或指定文檔類型（interview、brief、presentation）

2. **將文檔放在指定路徑**
   - 路徑：`spec/brand_brief.md` 或 `spec/brand_documents/`
   - 支援格式：`.md`、`.txt`

**系統會自動調用 CIS Mapper API 提取品牌資訊**：

```tool
cloud_capability.call
capability: brand_identity
endpoint: cis-mapper/map
params:
  document_content: {從文件讀取或用戶提供的內容}
  document_type: {自動識別或用戶指定：interview, brief, presentation, other}
  workspace_id: {workspace_id}
  target_language: zh-TW
```

**CIS Mapper 會自動提取**：
- Brand MI（品牌心智）：vision, values, worldview, redlines
- Brand Personas（品牌受眾）：1-3 個主要受眾畫像
- Brand Storylines（品牌故事主軸）：1-3 個核心故事主題

**提取完成後**：
- 系統會自動將提取的品牌資產保存到資料庫
- 你可以在 Brand Workspace 中查看生成的品牌資產
- 後續步驟可以基於提取的資訊繼續完善

### 方式 B：透過對話收集（如果沒有現成文檔）

如果沒有現成的品牌文檔，請提供以下信息（可以是自然語言描述）：

1. **品牌基本信息**
   - 品牌名稱
   - 所屬行業
   - 創立時間（如適用）

2. **目標受眾**
   - 主要客戶群是誰？
   - 他們的痛點是什麼？

3. **競品參考**
   - 有哪些競品？
   - 你希望跟他們有什麼不同？

4. **現有素材**（可選）
   - 現有的品牌描述
   - 之前的 VI 素材
   - 參考圖片或網站

### 工具調用

```tool
filesystem_read_file
path: spec/brand_brief.md
```

如果找到 `spec/brand_brief.md`，會自動調用 CIS Mapper API 處理。

如果沒有現成的品牌簡報，我會根據對話內容整理。

---

## Step 2: 世界觀探索 🟡

基於品牌背景，我會為你生成 **3-5 套候選世界觀**。

### AI 產出

```yaml
worldview_options:
  - option_id: wv_1
    name: "探索者"
    description: "品牌是引領用戶探索未知的嚮導，強調發現、創新、邊界突破"
    key_metaphors: ["航海", "星際探索", "地圖"]
    visual_direction: "深色背景，星空元素，動態粒子"

  - option_id: wv_2
    name: "守護者"
    description: "品牌是用戶可靠的夥伴，強調安全、信任、長期陪伴"
    key_metaphors: ["燈塔", "盾牌", "家"]
    visual_direction: "溫暖色調，圓潤形狀，穩重感"

  - option_id: wv_3
    name: "變革者"
    description: "品牌是推動改變的力量，強調顛覆、重塑、新可能"
    key_metaphors: ["破繭", "重生", "火焰"]
    visual_direction: "對比強烈，幾何切割，動態張力"
```

### 決策卡：品牌世界觀選擇

```decision_card
card_id: dc_worldview
type: stance
title: "品牌世界觀選擇"
question: "你希望品牌傳達什麼樣的世界觀？"
options: [以上選項]
```

**請品牌方選擇最符合品牌願景的世界觀。**

---

## Step 3: 價值主張定義 🟡

基於選定的世界觀，我會幫你提煉價值主張。

### AI 分析

```yaml
value_proposition:
  core_value: "[基於世界觀提煉]"

  differentiation:
    vs_competitor_a: "他們強調 X，我們強調 Y"
    vs_competitor_b: "他們的用戶是 X，我們的用戶是 Y"

  tagline_options:
    - "[選項 1]"
    - "[選項 2]"
    - "[選項 3]"
```

### 人類決策

品牌方確認：
- [ ] 核心價值是否準確
- [ ] 差異化是否足夠
- [ ] 選擇一個 tagline 方向

---

## Step 4: 品牌紅線設定 🔴

> ⚠️ **這一步如果沒有人做，代表的是：你的品牌讓 AI 自己決定立場與責任。**

### AI 參考建議

我可以列出常見的品牌紅線供參考：

```yaml
common_redlines:
  ethics:
    - "不做虛假宣傳"
    - "不使用爭議性素材"
    - "不傷害環境或動物"

  politics:
    - "不與特定政治立場掛鉤"
    - "不參與政治爭議話題"

  business:
    - "不做惡意競爭"
    - "不犧牲用戶利益換取短期收益"

  content:
    - "不使用歧視性語言"
    - "不傳播未經證實的信息"
```

### 決策卡：品牌紅線

```decision_card
card_id: dc_redlines
type: stance
title: "【立場卡】我們永遠不做什麼？"
question: "請列出品牌的紅線，這將決定品牌的底線與信譽"
requires_signature: true
reminder: "我願意為這個立場負責"
```

**品牌方請親自填寫並簽核：**

```yaml
brand_redlines:
  - "[紅線 1]"
  - "[紅線 2]"
  - "[紅線 3]"

signed_by: "[簽核人]"
signed_at: "[日期]"
```

---

## Step 5: 品牌人格塑造 🟡

基於世界觀和價值主張，定義品牌的人格特質。

### AI 產出

```yaml
personality_options:
  traits:
    - option_set_a: ["專業", "友善", "創新"]
    - option_set_b: ["前衛", "大膽", "有態度"]
    - option_set_c: ["溫暖", "可靠", "親切"]

  tone_of_voice:
    formal_casual: 0.4  # 0=極正式, 1=極休閒
    serious_playful: 0.3
    professional_friendly: 0.6

  tone_examples:
    greeting: "嗨！歡迎來到 [品牌名]"
    error: "抱歉，出了點小狀況。我們正在處理..."
    success: "太棒了！你成功完成了 [動作]"
```

### 人類決策

品牌方選擇人格特質組合：
- [ ] 特質組合選擇
- [ ] 語氣刻度確認

設計師將人格轉化為：
- [ ] 視覺風格方向
- [ ] 設計語言建議

---

## 產出物

完成本階段後，會生成以下文件：

```
spec/
├── mind_identity/
│   ├── worldview.md           # 世界觀定義
│   ├── value_proposition.md   # 價值主張
│   ├── brand_redlines.md      # 品牌紅線 (🔴 需簽核)
│   ├── personality.md         # 品牌人格
│   └── tone_of_voice.md       # 語氣指南
└── decisions/
    └── mi_decisions.json      # 決策紀錄
```

---

## 進入下一階段

完成 MI 品牌心智後，可以進入：

1. **BI 行為場景** - 定義品牌如何溝通、應對
2. **VI 視覺系統** - 定義品牌的外表

選擇下一步，或繼續完善當前階段。

