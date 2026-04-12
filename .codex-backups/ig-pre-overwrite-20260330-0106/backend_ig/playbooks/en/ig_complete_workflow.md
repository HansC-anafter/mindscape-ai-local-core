---
playbook_code: ig_complete_workflow
version: 1.0.0
capability_code: instagram
name: IG Complete Workflow
description: Orchestrate multiple playbooks in sequence to execute end-to-end workflows
tags:
  - instagram
  - workflow
  - orchestration
  - automation

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_complete_workflow_tool

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🔄
---

# IG Complete Workflow

## Goal

Orchestrate multiple playbooks in sequence to execute end-to-end workflows for IG Post creation, review, and publishing.

## Functionality

This Playbook will:

1. **Execute Workflow**: Execute a predefined workflow with multiple steps
2. **Create Post Workflow**: Create a new post following complete workflow
3. **Review Workflow**: Execute review workflow for existing post

## Use Cases

- Execute complete post creation workflow
- Orchestrate multiple playbooks in sequence
- Automate end-to-end post publishing process
- Manage post review workflows

## Inputs

- `action`: Action to perform - "execute_workflow", "create_post_workflow", or "review_workflow" (required)
- `vault_path`: Path to Obsidian Vault (required)
- `workflow_name`: Name of the workflow (required for execute_workflow action)
- `workflow_steps`: List of workflow steps (required for execute_workflow action)
- `initial_context`: Initial context variables (optional)
- `post_content`: Post content (required for create_post_workflow action)
- `post_metadata`: Post metadata/frontmatter (required for create_post_workflow action)
- `target_folder`: Target folder for post (default: 20-Posts)
- `post_path`: Path to post file (required for review_workflow action)
- `review_notes`: List of review notes (optional)

## Outputs

- `result`: Workflow execution result with step results and final context

## Workflow Actions

1. **execute_workflow**: Execute a predefined workflow with multiple steps
2. **create_post_workflow**: Create a new post following complete workflow
3. **review_workflow**: Execute review workflow for existing post

## Steps (Conceptual)

1. Execute workflow based on selected action
2. Run workflow steps in sequence
3. Collect results and return final context

## Notes

- Supports custom workflow definitions
- Can orchestrate multiple playbooks
- Maintains context across workflow steps

