---
playbook_code: sonic_usage_analytics
version: 1.0.0
locale: en
name: "Usage Tracking & Effectiveness Analysis"
description: "Material → Scene → Effectiveness correlation (Audio BI)"
kind: user_workflow
capability_code: sonic_space
---

# Usage Tracking & Effectiveness Analysis

Material → Scene → Effectiveness correlation (Audio BI)

## Overview

The Usage Analytics playbook tracks and analyzes how audio assets are used across the system. It provides insights into asset popularity, usage patterns, and user behavior.

**Key Features:**
- Track asset usage
- Analyze usage patterns
- Generate usage reports
- Provide usage insights

**Purpose:**
This playbook enables users to understand how audio assets are being used, identify popular assets, and gain insights into usage patterns for better asset management and curation.

**Related Playbooks:**
- `sonic_navigation` - Track navigation usage
- `sonic_decision_trace` - Analyze decision patterns
- `sonic_dataset_curation` - Use analytics for curation

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_usage_analytics.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Collect Usage Data

Collect material → scene → effectiveness data

- **Action**: `collect_usage_data`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Analyze Correlation

Analyze Audio BI correlations

- **Action**: `analyze_correlation`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

No guardrails defined.

## Required Capabilities

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## Data Locality

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## Use Cases

1. **Usage Tracking**
   - Track which assets are used most
   - Identify popular sounds
   - Monitor usage patterns

2. **Analytics Reports**
   - Generate usage reports
   - Analyze usage trends
   - Provide insights for curation

3. **Asset Management**
   - Use analytics for asset prioritization
   - Identify underutilized assets
   - Optimize asset library

## Examples

### Example 1: Generate Usage Report

```json
{
  "time_range": "last_30_days",
  "report_type": "asset_popularity"
}
```

**Expected Output:**
- Usage analytics report
- Asset popularity rankings
- Usage pattern insights

## Technical Details

**Analytics Tracking:**
- Tracks asset usage across system
- Records usage events
- Analyzes usage patterns
- Generates insights

**Tool Dependencies:**
- Analytics and reporting system

## Related Playbooks

- **sonic_navigation** - Track navigation usage
- **sonic_decision_trace** - Analyze decision patterns
- **sonic_dataset_curation** - Use analytics for curation

## Reference

- **Spec File**: `playbooks/specs/sonic_usage_analytics.json`
