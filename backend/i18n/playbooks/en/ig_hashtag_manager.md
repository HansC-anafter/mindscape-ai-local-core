---
playbook_code: ig_hashtag_manager
version: 1.0.0
name: IG Hashtag Manager
description: Manage hashtag groups and combine hashtags for IG posts based on intent, audience, and region
tags:
  - instagram
  - hashtags
  - social-media
  - marketing

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_hashtag_manager_tool

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: writer
icon: #
capability_code: instagram
---

# IG Hashtag Manager

## Goal

Manage hashtag groups and intelligently combine hashtags for IG posts based on post intent, target audience, and region. Supports hashtag blocking and compliance checking.

## Functionality

This Playbook will:

1. **Load Hashtag Groups**: Load predefined hashtag groups (brand fixed, theme, campaign)
2. **Combine Hashtags**: Combine hashtags based on intent, audience, and region
3. **Check Blocked**: Check if hashtags are in blocked list

## Use Cases

- Generate hashtag recommendations for IG posts
- Combine hashtags from multiple groups
- Check hashtag compliance and blocking
- Manage hashtag groups for campaigns

## Inputs

- `intent`: Post intent - "教育" (education), "引流" (traffic), "轉換" (conversion), or "品牌" (brand) (optional)
- `audience`: Target audience (optional)
- `region`: Region (optional)
- `hashtag_count`: Required hashtag count - 15, 25, or 30 (default: 25)
- `action`: Action to perform - "recommend", "combine", or "check_blocked" (default: "recommend")
- `hashtags`: List of hashtags to check (required for check_blocked action)

## Outputs

- `hashtag_groups`: Hashtag groups (brand fixed, theme, campaign)
- `recommended_hashtags`: Recommended hashtag list
- `blocked_hashtags`: Blocked hashtags found
- `hashtag_groups_used`: Hashtag groups used in combination
- `total_count`: Total hashtag count

## Steps (Conceptual)

1. Load hashtag groups from configuration
2. Combine hashtags based on intent, audience, and region
3. Check for blocked hashtags if provided

## Notes

- Supports multiple hashtag count options (15, 25, 30)
- Automatically includes brand fixed hashtags
- Can check hashtag compliance against blocked list

