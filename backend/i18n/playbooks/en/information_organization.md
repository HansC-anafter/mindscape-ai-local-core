---
playbook_code: information_organization
version: 1.0.0
name: Information Organization & Knowledge Base
description: Organize and categorize research information by collecting scattered information, identifying topics and categories, building knowledge architecture, categorizing and tagging, and generating structured knowledge base
tags:
  - research
  - organization
  - knowledge
  - information

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - semantic_seeds.extract_seeds
  - core_llm.structured_extract

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: researcher
icon: 🗂️
---

# Information Organization & Knowledge Base - SOP

## Goal
Help users organize and categorize research information by collecting scattered information, identifying topics and categories, building knowledge architecture, categorizing and tagging, and generating a structured knowledge base.

## Execution Steps

### Phase 1: Collect Scattered Information
- Ask user to provide research information (files, URLs, or text)
- Collect information from different sources
- Understand the research domain and context
- Identify information types and formats
- Organize raw information by source

### Phase 2: Identify Topics and Categories
- Analyze information to identify main topics
- Extract key themes and subject areas
- Recognize sub-topics and related concepts
- Group similar information together
- Create initial category structure

### Phase 3: Build Knowledge Architecture
- Design hierarchical knowledge structure
- Create categories and subcategories
- Establish relationships between topics
- Define taxonomy and classification system
- Organize information by domain or field

### Phase 4: Categorize and Tag
- Assign information to appropriate categories
- Add relevant tags and keywords
- Create cross-references between related items
- Apply consistent tagging conventions
- Ensure proper classification

### Phase 5: Generate Knowledge Base
- Create structured knowledge base document
- Organize information by categories
- Include metadata (tags, categories, sources)
- Generate index and navigation structure
- Provide searchable knowledge repository

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "researcher", emphasize academic organization and citation
- **Work Style**: If prefers "structured", provide detailed taxonomy and classification
- **Detail Level**: If prefers "high", include more granular categorization

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Build research knowledge base"), explicitly reference it in responses:
> "Since you're working towards 'Build research knowledge base', I recommend organizing information around..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `research_synthesis` - Use synthesis results to organize knowledge base
- `note_organization` - Similar process for learning notes

## Success Criteria
- Scattered information is collected and organized
- Topics and categories are identified
- Knowledge architecture is established
- Information is properly categorized and tagged
- Structured knowledge base is generated
- User has a searchable and organized knowledge repository

