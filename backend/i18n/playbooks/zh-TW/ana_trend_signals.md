# 趨勢訊號偵測

## 目的

透過分析內容特徵隨時間的變化來偵測新興趨勢訊號。此 playbook 幫助識別上升中的模式、衰退的趨勢，以及調整內容策略的最佳時機。

## 使用時機

- 月度/季度內容策略檢討期間
- 注意到互動模式發生變化時
- 規劃季節性活動前
- 累積足夠歷史數據後

## 輸入

- **feature_refs**（必填）：帶有時間戳記的內容/視覺特徵引用陣列
  - 每個 ref 應包含 timestamp 以進行時間線分析
- **time_window_days**（選填）：要分析的天數（預設：30）

## 流程

1. **時間線聚合**：按時間順序排序和分析特徵
2. **模式偵測**：識別上升和下降的模式
3. **洞察萃取**：生成以趨勢為焦點的可執行洞察

## 輸出

- **timeline_analysis**：特徵演變的時間順序分析
  - 包含視覺 token 和情緒數據的時間點
  - 變化指標
- **trend_insights**：包含規劃建議的可執行洞察

## 使用範例

```yaml
inputs:
  feature_refs:
    - source: "competitor_content"
      timestamp: "2026-01-01T00:00:00Z"
      features:
        visual_tokens: ["neon", "gradient"]
        dominant_mood: "energetic"
    - source: "competitor_content"
      timestamp: "2026-01-15T00:00:00Z"
      features:
        visual_tokens: ["soft", "organic", "gradient"]
        dominant_mood: "calm"
  time_window_days: 30
```

## 相關 Playbook

- `ana_competitor_style`：趨勢驗證的詳細風格分析
- `content_calendar_planning`：將趨勢洞察應用於日曆
- `ana_content_gap`：結合缺口分析進行策略定位
