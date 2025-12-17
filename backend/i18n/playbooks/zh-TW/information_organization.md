---
playbook_code: information_organization
version: 1.0.0
name: 資訊組織與知識庫
description: 組織和分類研究資訊，透過收集零散資訊、識別主題和類別、建立知識架構、分類和標籤，並生成結構化知識庫
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
  - sandbox.write_file
  - sandbox.read_file
  - filesystem_write_file
  - filesystem_read_file
  - semantic_seeds.extract_seeds
  - core_llm.structured_extract

language_strategy: model_native
locale: zh-TW
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

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存知識庫文檔
**必須**使用 `sandbox.write_file` 工具保存知識庫文檔（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `knowledge_base.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的結構化知識庫，包含所有分類、標籤和資訊
- 格式: Markdown 格式

#### 步驟 6.2: 保存分類體系
**必須**使用 `sandbox.write_file` 工具保存分類體系（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `taxonomy.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 分類體系和標籤系統的完整文檔
- 格式: Markdown 格式

## Success Criteria
- Scattered information is collected and organized
- Topics and categories are identified
- Knowledge architecture is established
- Information is properly categorized and tagged
- Structured knowledge base is generated
- User has a searchable and organized knowledge repository
- All knowledge base documents are saved to files for future reference
