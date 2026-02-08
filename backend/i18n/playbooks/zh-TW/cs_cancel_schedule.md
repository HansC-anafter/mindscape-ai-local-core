# 取消排程

## 目的

在分發前取消待處理的排程內容項目。

## 使用時機

- 內容發布前需要修改
- 計畫變更不再需要發布
- 緊急內容暫停

## 輸入

- **schedule_id**（必填）：要取消的排程 ID
- **reason**（選填）：取消原因供追蹤

## 輸出

- **success**：取消是否成功
- **previous_status**：取消前狀態
- **new_status**：新狀態（cancelled）

## 使用範例

```yaml
inputs:
  schedule_id: "abc123-def456"
  reason: "內容需要修改"
```

## 說明

- 只有待處理的排程可以取消
- 已分發或已完成的排程無法取消
- 取消會記錄在帳本中供稽核

## 相關 Playbook

- `cs_create_schedule`：建立排程
- `cs_view_calendar`：檢視目前排程
