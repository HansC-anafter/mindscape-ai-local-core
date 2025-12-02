---
playbook_code: technical_documentation
version: 1.0.0
name: 技術文檔生成
description: 為程式碼生成技術文檔，透過分析程式碼結構和功能、提取 API 和函數描述、生成文檔結構、編寫使用範例，並生成完整文檔
tags:
  - documentation
  - code
  - technical
  - development

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_files.extract_text
  - core_llm.generate

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: reviewer
icon: 📖
---

# Technical Documentation Generation - SOP

## Goal
Help users generate technical documentation for code by analyzing code structure and functionality, extracting API and function descriptions, generating documentation structure, writing usage examples, and generating complete documentation.

## Execution Steps

### Phase 1: Analyze Code Structure and Functionality
- Extract code from files or receive code input
- Analyze overall code architecture and organization
- Identify modules, classes, and functions
- Understand code functionality and purpose
- Map dependencies and relationships

### Phase 2: Extract API and Function Descriptions
- Extract function signatures and parameters
- Identify API endpoints and methods
- Extract class and module descriptions
- Document input/output types and formats
- Note any configuration or setup requirements

### Phase 3: Generate Documentation Structure
- Design documentation hierarchy
- Create sections for overview, API reference, examples, etc.
- Organize content by modules or features
- Plan navigation and cross-references
- Define documentation format and style

### Phase 4: Write Usage Examples
- Create practical usage examples for each API/function
- Include common use cases and scenarios
- Provide code snippets and demonstrations
- Show error handling and edge cases
- Include integration examples if applicable

### Phase 5: Generate Complete Documentation
- Compile all documentation sections
- Create comprehensive technical documentation with:
  - Overview and introduction
  - Installation and setup guide
  - API reference documentation
  - Usage examples and tutorials
  - Configuration and customization
  - Troubleshooting and FAQ
- Ensure consistency and completeness

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "developer", emphasize practical examples and integration guides
- **Work Style**: If prefers "structured", provide detailed API reference
- **Detail Level**: If prefers "high", include more technical details and advanced usage

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Complete API documentation"), explicitly reference it in responses:
> "Since you're working towards 'Complete API documentation', I recommend focusing on documenting the core APIs first..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `code_review` - Use code review results to inform documentation priorities
- `content_editing` - Edit and refine documentation after generation

## Success Criteria
- Code structure and functionality are analyzed
- API and function descriptions are extracted
- Documentation structure is generated
- Usage examples are written
- Complete technical documentation is generated
- User has comprehensive, well-organized documentation
