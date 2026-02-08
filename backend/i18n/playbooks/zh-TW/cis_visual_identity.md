# 👁 VI 視覺系統

> **你現在看到的是 *草稿宇宙*，還不是可以直接扛十年的 CIS。**

## 目標

建立品牌的完整視覺識別系統，包括：
- Moodboard 與視覺方向
- Logo 宇宙
- 色彩系統
- 字體系統
- 版式與 Grid
- 應用模板

## 責任分配

| 步驟 | 責任 | AI 角色 | 設計師角色 |
|------|------|---------|------------|
| Moodboard | 🟢 AI自動 | 大量草圖生成 | 審核方向 |
| Logo | 🟡 AI提案 | 生成多種變體 | 系統化規範 |
| 色彩系統 | 🟡 AI提案 | 提取配色方案 | **CMYK調整、競品避開** |
| **字體系統** | 🔴 Only Human | 推薦參考 | **授權、可讀性、跨平台** |
| 版式 Grid | 🟡 AI提案 | 生成 mockup | 建立規範 |
| 應用模板 | 🟢 AI自動 | 批量生成 | 審核品質 |

---

## Step 1: Moodboard 探索 🟢

基於 MI 品牌心智，自動生成視覺方向探索。

### 讀取品牌心智

```tool
filesystem_read_file
path: spec/mind_identity/worldview.md
```

```tool
filesystem_read_file
path: spec/mind_identity/personality.md
```

### AI 產出

```yaml
moodboard:
  primary_direction:
    mood: "[基於世界觀]"
    keywords: ["futuristic", "elegant", "dynamic"]
    color_feeling: "深色基底，帶有科技感的漸層"
    texture: "光滑、精緻、有未來感"

  reference_styles:
    - style_name: "Cosmic Tech"
      description: "深邃宇宙感，粒子動態效果"
      reference_images: [...]

    - style_name: "Minimal Future"
      description: "極簡未來主義，大量留白"
      reference_images: [...]

    - style_name: "Warm Innovation"
      description: "溫暖但有科技感，人文與技術平衡"
      reference_images: [...]
```

---

## Step 2: Logo 宇宙 🟡

### AI 產出：Logo 概念

```yaml
logo_concepts:
  - concept_id: logo_1
    name: "Abstract Symbol"
    description: "抽象符號，代表品牌核心概念"
    variations:
      - primary: "[主 Logo]"
      - horizontal: "[橫式]"
      - vertical: "[直式]"
      - icon: "[圖標]"
      - monochrome: "[單色]"

  - concept_id: logo_2
    name: "Wordmark"
    description: "字標設計，強調品牌名稱"
    variations: [...]

  - concept_id: logo_3
    name: "Combination Mark"
    description: "圖標 + 字標組合"
    variations: [...]
```

### 設計師需要做的（AI 無法判斷）

```yaml
designer_tasks:
  - task: "比例規範"
    reason: "確保不同尺寸下的視覺平衡"

  - task: "安全空間定義"
    reason: "保護 Logo 的識別度"

  - task: "最小尺寸限制"
    reason: "確保印刷清晰度"

  - task: "誤用示例"
    reason: "預防常見錯誤使用"
```

### 版本對比啟用

此步驟啟用 **AI vs 設計師版本對比**，記錄設計師的專業判斷。

---

## Step 3: 色彩系統 🟡

### AI 產出：配色方案

```yaml
color_palette_options:
  - palette_id: palette_1
    name: "Deep Space"
    colors:
      primary: "#0a0a2a"
      secondary: "#1a1a4a"
      accent: "#ffa0e0"
      neutral: ["#ffffff", "#f5f5f5", "#e0e0e0", "#333333"]
    semantic:
      success: "#22c55e"
      warning: "#eab308"
      error: "#ef4444"
      info: "#3b82f6"

  - palette_id: palette_2
    name: "Warm Tech"
    colors:
      primary: "#1a1a2e"
      secondary: "#16213e"
      accent: "#e94560"
      neutral: [...]
```

### 設計師需要做的（AI 無法判斷）

```yaml
designer_notes:
  - area: "印刷友善調整"
    ai_approach: "直接使用 RGB 值"
    designer_change: "轉換為 CMYK 友善值"
    reason: "AI 不會考慮 CMYK 轉換後的色差，某些螢幕色在印刷時會失真"

  - area: "競品迴避"
    ai_approach: "基於美學選擇配色"
    designer_change: "調整與競品 B 過度相似的色調"
    reason: "需要市場脈絡，AI 不知道你的競品是誰"

  - area: "色彩使用規則"
    ai_approach: "提供色板"
    designer_change: "定義什麼情況用什麼顏色"
    reason: "確保團隊成員有統一的使用標準"
```

### 輸出

```tool
filesystem_write_file
path: spec/visual_identity/color_palette.md
content: |
  # 色彩系統

  ## 主色板
  - Primary: #0a0a2a
  - Secondary: #1a1a4a
  - Accent: #ffa0e0

  ## 印刷安全版本 (由設計師調整)
  - Primary (CMYK): C:95 M:90 Y:30 K:70
  - Accent (CMYK): C:0 M:45 Y:0 K:0

  ## 使用規則
  - Primary: 背景、大面積區塊
  - Accent: CTA、重點強調，每頁面不超過 3 處
  - Neutral: 文字、分隔線
```

---

## Step 4: 字體系統 🔴

> ⚠️ **這是 Only Human 步驟。字體選擇涉及授權費用、可讀性、品牌調性，AI 無法綜合判斷。**

### AI 參考建議

我可以提供符合品牌調性的字體推薦：

```yaml
font_recommendations:
  heading_options:
    - name: "Space Grotesk"
      style: "現代幾何感"
      license: "Open Font License (免費)"
      web_support: "Google Fonts"

    - name: "Satoshi"
      style: "現代人文主義"
      license: "Fontshare (免費商用)"
      web_support: "Self-host"

    - name: "Geist"
      style: "科技極簡"
      license: "Open Source"
      web_support: "CDN available"

  body_options:
    - name: "Inter"
      style: "高可讀性"
      license: "Open Font License"

    - name: "Plus Jakarta Sans"
      style: "友善現代"
      license: "Open Font License"
```

### 設計師必須決定

```yaml
typography_decisions:
  - decision: "字體家族選擇"
    considerations:
      - "授權成本（商業用途）"
      - "中英文搭配效果"
      - "網頁加載性能"
      - "可及性（閱讀障礙友善）"

  - decision: "字級層級設計"
    considerations:
      - "確保長文可讀性"
      - "考慮目標用戶年齡層"
      - "響應式縮放規則"

  - decision: "行高與字距"
    considerations:
      - "中文與英文的最佳行高不同"
      - "標題與內文的字距差異"
```

### 設計師輸出

請設計師填寫：

```yaml
typography_system:
  heading_font: "[設計師選擇]"
  body_font: "[設計師選擇]"
  accent_font: "[可選]"

  type_scale:
    h1: "48px / 56px"
    h2: "36px / 44px"
    h3: "24px / 32px"
    body: "16px / 24px"
    caption: "14px / 20px"

  line_heights:
    heading: 1.2
    body: 1.5

  font_licenses:
    heading_font: "[授權類型]"
    body_font: "[授權類型]"
```

---

## Step 5: 版式與 Grid 🟡

### AI 產出：版式建議

```yaml
layout_options:
  - layout_id: grid_12
    name: "12 欄系統"
    columns: 12
    gutter: "24px"
    margin: "auto"
    max_width: "1200px"
    breakpoints:
      sm: "640px"
      md: "768px"
      lg: "1024px"
      xl: "1280px"

  - layout_id: grid_fluid
    name: "流體系統"
    description: "更靈活的響應式佈局"
```

### 設計師補充

設計師建立完整的 Grid 規範和間距系統。

---

## Step 6: 應用模板 🟢

基於以上所有規範，自動生成應用模板。

### AI 產出

```yaml
templates:
  - type: "social_post"
    sizes:
      - "Instagram Post (1080x1080)"
      - "Instagram Story (1080x1920)"
      - "Twitter Post (1200x675)"
      - "LinkedIn Post (1200x627)"
    preview: "[模板預覽]"

  - type: "presentation"
    format: "16:9"
    slides:
      - "Title Slide"
      - "Content Slide"
      - "Image + Text"
      - "Quote"
      - "Thank You"
    preview: "[模板預覽]"

  - type: "business_card"
    size: "90x50mm"
    preview: "[模板預覽]"

  - type: "email_signature"
    preview: "[模板預覽]"
```

---

## 產出物

完成本階段後，會生成以下文件：

```
spec/
├── visual_identity/
│   ├── moodboard/              # 視覺方向
│   │   └── direction.md
│   ├── logo/                   # Logo 宇宙
│   │   ├── concepts.md
│   │   ├── usage_guide.md
│   │   └── assets/
│   ├── color_palette.md        # 色彩系統
│   ├── typography.md           # 字體系統 (🔴 設計師產出)
│   ├── layout_grid.md          # 版式系統
│   └── templates/              # 應用模板
│       ├── social/
│       ├── presentation/
│       └── business_card/
├── designer_notes/
│   └── vi_notes.json           # 設計師註解
└── version_compare/
    └── vi_compare.json         # AI vs 設計師對比
```

---

## 進入下一階段

完成 VI 視覺系統後，可以進入：

1. **決策工作坊** - 完成所有決策卡簽核
2. **Lens 打包** - 將 CIS 打包成可複用的 Brand Lens

選擇下一步，或繼續完善當前階段。

