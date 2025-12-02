---
playbook_code: execution_status_query
name: Execution Status Query
description: Playbook for querying task execution status and progress. Automatically queries detailed status of related executions and generates reports when users ask about task progress.
kind: system_tool
version: 1.0.0
locale: en
tags: [system, query, execution]
---

# Execution Status Query

## Description

Playbook for querying task execution status and progress. Automatically queries detailed status of related executions and generates reports when users ask about task progress.

## Features

- Extract query intent from natural language
- Automatically match relevant executions
- Query execution status and steps
- Generate structured summary and natural language report

## Use Cases

- "How is the progress of that task?"
- "Where are we in the execution?"
- "Is that export task completed?"

## Inputs

- `user_message`: User's query message
- `workspace_id`: Workspace ID
- `conversation_context`: Conversation context (optional)
- `execution_id`: Direct execution ID (optional, skips candidate selection)

## Outputs

- `summary`: Structured execution status summary (for machine use)
- `report`: Natural language status report (for human reading)
- `execution_id`: Queried execution ID

