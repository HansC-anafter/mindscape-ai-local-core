# 批次排程

## 目的

批次排程多個內容項目，自動分配發布時間。支援平均分配、尖峰時段優化或自訂時間。

## 使用時機

- 一次排程一週的內容
- 優化發文時間以提高互動
- 從規劃匯入批量內容日曆

## 輸入

- **items**（必填）：要排程的內容項目列表
- **distribution_strategy**（必填）：
  - `type`：分配類型（even、peak_hours、custom）
  - `start_time`：分配時段開始
  - `end_time`：分配時段結束
  - `peak_hours`：尖峰時段（0-23）用於 peak_hours 策略

## 分配策略

### 平均分配（Even）
在時段內平均分配項目。

### 尖峰時段（Peak Hours）
在指定的高互動時段排程項目。

### 自訂（Custom）
為每個項目使用提供的自訂時間。

## 輸出

- **scheduled_count**：已排程項目數
- **items**：包含時間的已排程項目列表

## 使用範例

```yaml
inputs:
  items:
    - content_ref: { pack: "ig", asset_id: "post_001" }
      target_platform: "ig"
    - content_ref: { pack: "ig", asset_id: "post_002" }
      target_platform: "ig"
  distribution_strategy:
    type: "peak_hours"
    start_time: "2026-01-22T00:00:00Z"
    end_time: "2026-01-28T23:59:59Z"
    peak_hours: [9, 12, 18, 21]
```

## 相關 Playbook

- `cs_create_schedule`：建立單一排程
- `cs_view_calendar`：檢視結果日曆
