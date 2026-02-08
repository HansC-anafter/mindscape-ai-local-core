# 內容缺口分析

## 目的

透過比較你的內容特徵與追蹤對象/競品內容來識別內容缺口。此 playbook 幫助發現競品使用但你尚未探索的主題、格式和視覺風格。

## 使用時機

- 透過 ig.sync_content 同步競品/追蹤內容後
- 內容日曆規劃期間
- 尋找新內容創意時
- 啟動新內容系列前

## 輸入

- **own_content_ref**（必填）：你的內容分析數據引用
  - 可包含 topics、formats、visual_tokens、tags
- **following_content_ref**（必填）：競品/追蹤內容分析引用
- **dimensions**（選填）：要分析的維度
  - `topic`：比較內容主題/主軸
  - `format`：比較內容格式（輪播、短影音、限時動態等）
  - `visual_style`：比較視覺元素和風格
  - `timing`：比較發文模式（尚未實作）
  - `engagement_pattern`：比較互動指標（尚未實作）

## 流程

1. **載入內容數據**：從兩個引用取得分析數據
2. **偵測缺口**：跨選定維度進行比較
3. **生成洞察**：建立可執行的建議與建議 playbook

## 輸出

- **gaps**：競品活躍但你尚未涉足的內容領域
- **opportunities**：值得探索的趨勢元素
- **strengths**：你獨特的內容元素
- **insights**：可供內容生成使用的可執行洞察

## 使用範例

```yaml
inputs:
  own_content_ref:
    topics: ["ai", "productivity", "tools"]
    formats: ["carousel", "image"]
    visual_tokens: ["minimalist", "gradient"]
  following_content_ref:
    topics: ["ai", "productivity", "automation", "workflow", "tutorials"]
    formats: ["carousel", "reel", "story"]
    visual_tokens: ["minimalist", "gradient", "3d", "neon"]
  dimensions:
    - topic
    - format
    - visual_style
```

## 相關 Playbook

- `ig_generate_post`：使用缺口洞察來創建新內容
- `content_drafting`：為識別的主題缺口生成內容
- `ana_competitor_style`：深入分析視覺風格差異
