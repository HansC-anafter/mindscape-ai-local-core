---
playbook_code: cis_lens_packaging
version: 1.0.0
name: Lens Packaging
description: Package completed CIS into reusable Brand Lens
tags:
  - brand
  - lens
  - packaging
  - cis

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.structured_extract
  - cloud_capability.call
  - filesystem_write_file

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: planner
icon: 📦
capability_code: brand_identity
---

# 📦 Lens Packaging

> **Package completed CIS into reusable Brand Lens, so all future outputs go through this "brand brain".**

## Goal

Package complete CIS (MI, BI, VI) into reusable Brand Lens for all future brand outputs.

## Responsibility Distribution

| Step | Responsibility | AI Role | Human Role |
|------|----------------|---------|------------|
| Collect CIS Components | 🟢 AI Auto | Collect all CIS data | Review completeness |
| Package Lens | 🟢 AI Auto | Generate Lens structure | Confirm final version |

---

## Step 1: Collect CIS Components

Collect all completed CIS components:
- MI (Brand Mind Identity)
- BI (Behavior Identity)
- VI (Visual Identity)

---

## Step 2: Package Brand Lens

Package all CIS components into Brand Lens.

---

## Step 3: Verify Lens

Verify that the packaged Brand Lens is complete and usable.







