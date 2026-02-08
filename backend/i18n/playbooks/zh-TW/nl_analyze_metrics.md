# 分析指標

## 目的

分析 campaign 寄送和互動指標，包括開信率、點擊率和基準比較。

## 使用時機

- 寄送 campaign 後
- 審核 campaign 成效
- 與業界基準比較

## 輸入

- **campaign_id**（必填）：要分析的 campaign
- **include_link_clicks**（選填）：包含連結點擊明細

## 輸出

- **metrics**：原始指標（已送達、已開啟、已點擊等）
- **rates**：計算的比率（open_rate、click_rate 等）
- **benchmarks**：業界平均比較
- **performance**：高於/低於基準評估

## 關鍵指標

- **開信率**：唯一開啟數 / 已送達數
- **點擊率**：唯一點擊數 / 已送達數
- **退信率**：退信數 / 總寄送數
- **退訂率**：退訂數 / 已送達數

## 使用範例

```yaml
inputs:
  campaign_id: "abc123"
  include_link_clicks: true
```

## 相關 Playbook

- `nl_send_campaign`：分析前先寄送
- `nl_create_campaign`：根據分析建立新 campaign
