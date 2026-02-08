---
playbook_code: cis_mind_identity
version: 1.0.0
name: MI Brand Mind Identity
description: Establish brand core mind model, including brand positioning, value proposition, worldview, and brand redlines
tags:
  - brand
  - mind-identity
  - positioning
  - worldview

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - cloud_capability.call
  - core_llm.generate
  - core_llm.structured_extract

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: consultant
icon: 🧠
capability_code: brand_identity
---

# 🧠 MI Brand Mind Identity

> **AI is responsible for "exploring possibilities", you and the designer are responsible for "deciding who you want to be".**

## Goal

Establish brand core mind model, including:
- Brand positioning and value proposition
- Brand worldview
- Brand redlines (things we never do)
- Brand personality and tone

## Responsibility Distribution

| Step | Responsibility | AI Role | Human Role |
|------|----------------|---------|------------|
| Worldview Exploration | 🟡 AI Proposal | Generate 3-5 candidate worldlines | Brand selects, designer translates to visual |
| Value Proposition | 🟡 AI Proposal | Analyze competitors, propose differentiation | Brand confirms core values |
| **Brand Redlines** | 🔴 Only Human | List possible "don't do" items | **Brand decides** |
| Brand Personality | 🟡 AI Proposal | Generate personality trait options | Brand selects, designer transforms |

---

## Step 1: Collect Brand Background

First, I need to understand the brand's basic information.

### Method A: Provide Existing Documents (Recommended)

If you already have brand-related documents (interviews, brand briefs, proposals, etc.), you can provide them directly.

**The system will automatically call CIS Mapper API to extract brand information.**

---

## Step 2: Explore Worldview

Based on brand information, generate 3-5 candidate worldlines.

---

## Step 3: Define Value Proposition

Analyze competitors and propose differentiated value proposition.

---

## Step 4: Define Brand Personality

Generate brand personality trait options.







