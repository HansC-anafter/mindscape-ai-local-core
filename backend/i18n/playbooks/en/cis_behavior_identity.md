---
playbook_code: cis_behavior_identity
version: 1.0.0
name: BI Behavior Identity
description: Establish brand behavior scenarios, including communication style, customer service scripts, crisis handling, and conflict positions
tags:
  - brand
  - behavior
  - communication
  - customer-service
  - crisis-management

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.generate
  - core_llm.structured_extract
  - cloud_capability.call

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: consultant
icon: 💬
capability_code: brand_identity
---

# 💬 BI Behavior Identity

> **Brand is not just visual, but also the tone and behavior of every interaction.**

## Goal

Establish brand behavior identity system, including:
- Communication style and tone
- Customer service scripts
- Crisis handling strategies
- Conflict positions

## Responsibility Distribution

| Step | Responsibility | AI Role | Human Role |
|------|----------------|---------|------------|
| Communication Style | 🟡 AI Proposal | Generate style options | Brand confirms |
| Customer Service Scripts | 🟡 AI Proposal | Generate script templates | Brand reviews |
| Crisis Handling | 🟡 AI Proposal | Generate strategy framework | Brand decides |
| Conflict Positions | 🔴 Only Human | List possible conflicts | **Brand decides** |

---

## Step 1: Define Communication Style

Based on MI Brand Mind Identity, define brand communication style.

---

## Step 2: Create Customer Service Scripts

Based on communication style, generate customer service script templates.

---

## Step 3: Define Crisis Handling Strategy

Establish standard crisis handling process for the brand.

---

## Step 4: Confirm Conflict Positions

Brand decides positions in various conflict situations.







