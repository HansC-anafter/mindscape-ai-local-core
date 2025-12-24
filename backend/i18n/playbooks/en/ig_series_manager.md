---
playbook_code: ig_series_manager
version: 1.0.0
name: IG Series Manager
description: Manage IG Post series including creation, updates, querying, and cross-referencing
tags:
  - instagram
  - series
  - organization
  - content-planning

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - ig_series_manager_tool

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: writer
icon: 📚
capability_code: instagram
---

# IG Series Manager

## Goal

Manage IG Post series including creation, adding posts, querying, and cross-referencing between posts in a series.

## Functionality

This Playbook will:

1. **Create Series**: Create new post series
2. **Add Post**: Add post to series
3. **Get Series**: Get series information
4. **List Series**: List all series
5. **Get Posts**: Get all posts in series
6. **Get Previous/Next**: Get previous and next posts in series
7. **Update Progress**: Update series progress

## Use Cases

- Organize posts into series
- Track series progress
- Navigate between series posts
- Manage multi-part content

## Inputs

- `action`: Action to perform - "create", "add_post", "get", "list", "get_posts", "get_previous_next", or "update_progress" (required)
- `vault_path`: Path to Obsidian Vault (required)
- `series_code`: Series code (required for most actions)
- `series_name`: Series name (required for create action)
- `description`: Series description (optional)
- `total_posts`: Total number of posts planned (optional)
- `post_path`: Post file path (required for add_post action)
- `post_slug`: Post slug (required for add_post action)
- `post_number`: Post number in series (optional, auto-increment if not provided)
- `current_post_number`: Current post number (required for get_previous_next action)

## Outputs

- `series`: Series information
- `series_list`: List of all series
- `posts`: List of posts in series
- `previous`: Previous post in series
- `next`: Next post in series

## Steps (Conceptual)

1. Create series or add posts to existing series
2. Query series information or list all series
3. Get previous/next posts for navigation
4. Update series progress

## Notes

- Supports auto-incrementing post numbers
- Enables cross-referencing between series posts
- Tracks series progress automatically

