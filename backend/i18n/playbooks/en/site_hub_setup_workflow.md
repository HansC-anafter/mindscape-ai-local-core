---
playbook_code: site_hub_setup_workflow
version: 1.0.0
capability_code: site_hub_integration
name: Site-Hub Setup (Workflow)
description: Set up Site-Hub runtime by executing tool slots directly (no LLM)
tags:
  - site-hub
  - runtime
  - integration

kind: user_workflow
visible_in:
  - workspace_playbook_menu

locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: false
---

This playbook runs the workflow spec directly:
- `site_hub_integration.site_hub_discover_runtime`
- `site_hub_integration.site_hub_register_runtime`
- (optional) `site_hub_integration.site_hub_list_channels`

