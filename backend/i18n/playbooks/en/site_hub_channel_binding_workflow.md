---
playbook_code: site_hub_channel_binding_workflow
version: 1.0.0
capability_code: site_hub_integration
name: Site-Hub Channel Binding (Workflow)
description: Bind Site-Hub channel to workspace by executing tool slots directly (no LLM)
tags:
  - site-hub
  - channel
  - binding

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
- `site_hub_integration.site_hub_get_console_kit_channels`
- `site_hub_integration.site_hub_bind_channel`

