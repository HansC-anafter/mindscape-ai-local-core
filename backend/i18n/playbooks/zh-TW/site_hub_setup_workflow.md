---
playbook_code: site_hub_setup_workflow
version: 1.0.0
capability_code: site_hub_integration
name: Site-Hub 設置（Workflow）
description: 以 tool slots 直接執行完成 Site-Hub runtime 設置（不依賴 LLM）
tags:
  - site-hub
  - runtime
  - integration

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
- `site_hub_integration.site_hub_discover_runtime`
- `site_hub_integration.site_hub_register_runtime`
- （可選）`site_hub_integration.site_hub_list_channels`

