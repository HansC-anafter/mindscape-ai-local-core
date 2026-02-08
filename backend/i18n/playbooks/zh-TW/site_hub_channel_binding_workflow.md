---
playbook_code: site_hub_channel_binding_workflow
version: 1.0.0
capability_code: site_hub_integration
name: Site-Hub Channel 綁定（Workflow）
description: 以 tool slots 直接執行完成 Channel 綁定（不依賴 LLM）
tags:
  - site-hub
  - channel
  - binding

kind: user_workflow
visible_in:
  - workspace_playbook_menu

locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: false
---

本 Playbook 會以 workflow spec 直接執行：
- `site_hub_integration.site_hub_get_console_kit_channels`
- `site_hub_integration.site_hub_bind_channel`

