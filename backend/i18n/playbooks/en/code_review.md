---
playbook_code: code_review
version: 1.0.0
name: Code Review & Quality Analysis
description: Review code quality and best practices by analyzing code structure, checking code quality, identifying potential issues, checking best practices, and generating review reports
tags:
  - code
  - review
  - quality
  - development

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
  - core_files.extract_text
  - core_llm.structured_extract

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: reviewer
icon: 💻
---

# Code Review & Quality Analysis - SOP

## Goal
Help users review code quality and best practices by analyzing code structure, checking code quality, identifying potential issues, checking best practices, and generating comprehensive review reports.

## Execution Steps

### Phase 1: Analyze Code Structure
- Extract code from files or receive code input
- Analyze overall code architecture and organization
- Check module and function organization
- Evaluate code structure and design patterns
- Identify structural issues or anti-patterns

### Phase 2: Check Code Quality
- Analyze code readability and maintainability
- Check naming conventions and consistency
- Evaluate code complexity and cyclomatic complexity
- Review error handling and exception management
- Assess code documentation and comments

### Phase 3: Identify Potential Issues
- Detect potential bugs and logic errors
- Identify security vulnerabilities
- Check for performance issues
- Find code smells and technical debt
- Highlight areas requiring refactoring

### Phase 4: Check Best Practices
- Verify adherence to coding standards
- Check language-specific best practices
- Review design patterns usage
- Evaluate testing coverage (if test files available)
- Assess dependency management

### Phase 5: Generate Review Report
- Compile all review findings
- Create structured review report with:
  - Code structure analysis
  - Quality assessment
  - Issues and recommendations
  - Best practices compliance
  - Prioritized action items
- Provide before/after suggestions for improvements

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "developer", emphasize practical improvements and maintainability
- **Work Style**: If prefers "structured", provide detailed checklists and priorities
- **Detail Level**: If prefers "high", include more granular code analysis

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Improve codebase quality"), explicitly reference it in responses:
> "Since you're working towards 'Improve codebase quality', I recommend focusing on high-priority issues first..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `technical_documentation` - Generate documentation after code review
- `content_editing` - Review code comments and documentation

### Phase 6: File Generation and Saving

#### Step 6.1: Save Code Review Report
**Must** use `sandbox.write_file` tool to save code review report (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `code_review_report.md` (relative path, relative to sandbox root)
- Content: Complete code review report, including:
  - Code quality assessment
  - Issue identification and categorization
  - Code structure analysis
  - Best practices compliance
- Format: Markdown format

#### Step 6.2: Save Issue Priority List
**Must** use `sandbox.write_file` tool to save issue priority list (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `issue_priority_list.md` (relative path, relative to sandbox root)
- Content: Prioritized list of issues and recommendations
- Format: Markdown format

#### Step 6.3: Save Improvement Suggestions
**Must** use `sandbox.write_file` tool to save improvement suggestions (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `improvement_suggestions.md` (relative path, relative to sandbox root)
- Content: Detailed improvement suggestions and refactoring recommendations
- Format: Markdown format

## Success Criteria
- Code structure is thoroughly analyzed
- Code quality is assessed
- Potential issues are identified
- Best practices compliance is checked
- Comprehensive review report is generated
- User has clear, prioritized action items

