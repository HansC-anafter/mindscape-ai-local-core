---
playbook_code: brand_monthly_review
version: 1.0.0
name: Brand Monthly Review
description: Regularly review brand output coverage and consistency, propose improvement suggestions
tags:
  - brand
  - review
  - analytics
  - consistency
  - improvement

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - cloud_capability.call
  - core_llm.analyze
  - core_llm.structured_extract

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: analyst
icon: 📊
capability_code: brand_identity
---

# 📊 Brand Monthly Review

> **Regularly review brand outputs, ensure consistency, and discover improvement opportunities.**

## Goal

Regularly review brand output coverage and consistency, propose improvement suggestions.

## Execution Flow

### Step 1: Collect Brand Outputs

Collect all brand outputs for the specified month/year.

### Step 2: Analyze Coverage

Analyze brand output coverage and consistency.

### Step 3: Generate Recommendations

Generate improvement recommendations based on coverage analysis.

---

## Inputs

- `workspace_id`: Workspace ID
- `month`: Month (1-12, optional)
- `year`: Year (optional)

## Outputs

- `coverage_analysis`: Coverage analysis
- `recommendations`: Improvement recommendations







