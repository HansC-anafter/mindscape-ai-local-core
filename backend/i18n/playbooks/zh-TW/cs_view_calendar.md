# 檢視日曆

## 目的

檢視排程內容日曆，支援篩選和依日期分組。

## 使用時機

- 審核即將發布的內容排程
- 檢查跨平台的排程狀態
- 規劃內容缺口

## 輸入

- **start_date**（選填）：開始日期 - 預設為今天
- **end_date**（選填）：結束日期 - 預設為開始後 30 天
- **platforms**（選填）：依平台篩選
- **status_filter**（選填）：依狀態篩選（pending、completed、failed、cancelled）

## 輸出

- **date_range**：日曆日期範圍
- **total_items**：範圍內的排程項目總數
- **dates**：依日期分組的項目
- **by_platform**：依平台計數
- **by_status**：依狀態計數

## 使用範例

```yaml
inputs:
  start_date: "2026-01-20"
  end_date: "2026-01-31"
  platforms: ["ig", "web"]
  status_filter: ["pending", "completed"]
```

## 相關 Playbook

- `cs_create_schedule`：建立新排程
- `cs_batch_schedule`：批次排程項目
