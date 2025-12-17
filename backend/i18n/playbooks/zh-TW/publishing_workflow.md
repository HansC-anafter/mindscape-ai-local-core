---
playbook_code: publishing_workflow
version: 1.0.0
name: 發布工作流程
description: 管理內容發布工作流程，透過檢查內容完整性、驗證格式和指南、生成發布檢查清單、準備發布說明，並規劃發布時程
tags:
  - publishing
  - workflow
  - content
  - management

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
  - core_llm.generate
optional_tools:
  - wp_sync.sync
  - voice_recording.transcribe

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: editor
icon: 📢
---

# Publishing Workflow - SOP

## Goal
Help users manage content publishing workflow by checking content completeness, validating format and guidelines, generating publishing checklist, preparing publishing notes, and planning publishing schedule.

## Execution Steps

### Phase 1: Check Content Completeness
- Verify all required content sections are present
- Check for missing information or placeholders
- Ensure all media assets are available and properly referenced
- Validate content structure and organization
- Confirm all links and references are valid

### Phase 2: Validate Format and Guidelines
- Check content format compliance (Markdown, HTML, etc.)
- Verify adherence to style guide and brand guidelines
- Validate metadata (title, description, tags, categories)
- Check image formats and sizes
- Ensure accessibility requirements are met

### Phase 3: Generate Publishing Checklist
- Create comprehensive pre-publishing checklist
- List all required elements and validations
- Prioritize checklist items by importance
- Include platform-specific requirements
- Provide completion status for each item

### Phase 4: Prepare Publishing Notes
- Generate publishing notes and changelog
- Prepare release notes or update descriptions
- Create social media announcement drafts
- Prepare email notifications (if applicable)
- Document any special considerations or warnings

### Phase 5: Plan Publishing Schedule
- Determine optimal publishing time based on audience
- Consider time zones and peak engagement times
- Plan content sequencing if multiple pieces
- Set up scheduling and reminders
- Coordinate with other content or campaigns

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "content manager", emphasize workflow efficiency and coordination
- **Work Style**: If prefers "structured", provide detailed checklists and schedules
- **Detail Level**: If prefers "high", include more granular validation steps

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Launch content marketing campaign"), explicitly reference it in responses:
> "Since you're working towards 'Launch content marketing campaign', I recommend scheduling publications to align with campaign milestones..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `content_editing` - Use editing results to prepare for publishing
- `seo_optimization` - Ensure SEO optimizations are applied before publishing
- `content_analysis` - Use analysis results to inform publishing strategy

## Integration with WordPress

If publishing to WordPress:
- Use `wp_sync.sync` to sync content to WordPress
- Validate WordPress-specific requirements
- Check plugin and theme compatibility
- Ensure proper category and tag assignment

## Integration with Voice Recording

If content includes audio files:
- Use `voice_recording.transcribe` to ensure transcripts are ready
- Verify audio quality and accessibility
- Prepare audio descriptions if needed

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存發布計劃
**必須**使用 `sandbox.write_file` 工具保存發布計劃（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `publishing_plan.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的發布計劃，包含檢查清單、發布說明和時程
- 格式: Markdown 格式

#### 步驟 6.2: 保存內容日曆
**必須**使用 `sandbox.write_file` 工具保存內容日曆（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `content_calendar.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 發布時程和內容序列規劃
- 格式: Markdown 格式

## Success Criteria
- Content completeness is verified
- Format and guidelines are validated
- Comprehensive publishing checklist is generated
- Publishing notes and announcements are prepared
- Publishing schedule is planned
- User has clear action items and timeline
- All publishing workflow documents are saved to files for future reference
