---
playbook_code: code_review
version: 1.0.0
name: 程式碼審查與品質分析
description: 審查程式碼品質和最佳實踐，透過分析程式碼結構、檢查程式碼品質、識別潛在問題、檢查最佳實踐，並生成審查報告
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
locale: zh-TW
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

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存審查報告
**必須**使用 `sandbox.write_file` 工具保存完整的程式碼審查報告（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `code_review_report.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的審查報告，包含：
  - 程式碼結構分析
  - 品質評估
  - 問題識別和建議
  - 最佳實踐合規性檢查
  - 優先級行動項目
- 格式: Markdown 格式，使用標題、列表和代碼塊

#### 步驟 6.2: 保存問題優先級列表
**必須**使用 `sandbox.write_file` 工具保存問題優先級列表（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `issues_priority.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 按優先級排序的問題列表，包含問題描述、嚴重程度和修復建議
- 格式: Markdown 格式

#### 步驟 6.3: 保存改進建議
**必須**使用 `filesystem_write_file` 工具保存詳細的改進建議：

- 文件路徑: `recommendations.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 具體的改進建議，包含 before/after 範例（如適用）
- 格式: Markdown 格式

## Success Criteria
- Code structure is thoroughly analyzed
- Code quality is assessed
- Potential issues are identified
- Best practices compliance is checked
- Comprehensive review report is generated
- User has clear, prioritized action items
- All review findings are saved to files for future reference
