---
playbook_code: execution_status_query
name: 執行狀態查詢
description: 查詢任務執行狀態和進度的 playbook。當用戶詢問任務進度時，自動查詢相關 execution 的詳細狀態並生成報告。
kind: system_tool
version: 1.0.0
locale: zh-TW
tags: [system, query, execution]
---

# 執行狀態查詢

## 描述

查詢任務執行狀態和進度的 playbook。當用戶詢問任務進度時，自動查詢相關 execution 的詳細狀態並生成報告。

## 功能

- 從自然語言中提取查詢意圖
- 自動匹配相關的 execution
- 查詢執行狀態和步驟
- 生成結構化摘要和自然語言報告

## 使用場景

- 「剛剛那個任務進度如何？」
- 「現在執行到哪裡了？」
- 「那個出檔任務完成了嗎？」

## 輸入

- `user_message`: 用戶的查詢訊息
- `workspace_id`: 工作區 ID
- `conversation_context`: 對話上下文（可選）
- `execution_id`: 直接指定 execution ID（可選，會跳過候選選擇）

## 輸出

- `summary`: 結構化執行狀態摘要（給機器用）
- `report`: 自然語言狀態報告（給人看）
- `execution_id`: 查詢的 execution ID

