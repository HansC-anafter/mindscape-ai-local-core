---
playbook_code: cis_visual_identity
version: 1.0.0
name: VI Visual Identity
description: Establish brand complete visual identity system, including moodboard, logo, color system, typography, layout, and application templates
tags:
  - brand
  - visual-identity
  - logo
  - color
  - typography
  - layout

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
  - filesystem_read_file
  - filesystem_write_file

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: designer
icon: 👁
capability_code: brand_identity
---

# 👁 VI Visual Identity

> **What you see now is a *draft universe*, not a CIS that can last ten years.**

## Goal

Establish brand complete visual identity system, including:
- Moodboard and visual direction
- Logo universe
- Color system
- Typography system
- Layout and Grid
- Application templates

## Responsibility Distribution

| Step | Responsibility | AI Role | Designer Role |
|------|----------------|---------|---------------|
| Moodboard | 🟢 AI Auto | Generate many sketches | Review direction |
| Logo | 🟡 AI Proposal | Generate multiple variants | Systematize specifications |
| Color System | 🟡 AI Proposal | Extract color schemes | **CMYK adjustment, avoid competitors** |
| **Typography System** | 🔴 Only Human | Recommend references | **Licensing, readability, cross-platform** |
| Layout Grid | 🟡 AI Proposal | Generate mockups | Establish specifications |
| Application Templates | 🟢 AI Auto | Batch generate | Review quality |

---

## Step 1: Moodboard Exploration 🟢

Based on MI Brand Mind Identity, automatically generate visual direction exploration.

---

## Step 2: Logo Universe 🟡

Generate logo variants based on moodboard.

---

## Step 3: Color System 🟡

Extract color palette from moodboard and brand context.

---

## Step 4: Typography System 🔴

Designer selects and specifies typography system.

---

## Step 5: Layout and Grid 🟡

Generate layout templates based on color and typography systems.

---

## Step 6: Application Templates 🟢

Generate application templates for various use cases.







