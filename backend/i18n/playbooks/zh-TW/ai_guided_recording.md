---
playbook_code: ai_guided_recording
version: 1.0.0
name: AI 引導課程錄製
description: 引導使用者完成課程錄製，透過準備課程大綱和腳本、設定錄製參數和提示、引導錄製過程、檢查錄製品質，並生成錄製報告
tags:
  - recording
  - course
  - production
  - audio

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
  - voice_recording.record_line
  - voice_recording.play_demo
  - voice_recording.transcribe
  - voice_recording.merge_recordings
optional_tools:
  - voice_recording.synthesize

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: course_producer
icon: 🎙️
---

# AI-Guided Course Recording - SOP

## Goal
Help users complete course recording with AI guidance by preparing course outline and script, setting recording parameters and prompts, guiding recording process, checking recording quality, and generating recording reports.

## Execution Steps

### Phase 1: Prepare Course Outline and Script
- Collect course outline and learning objectives
- Review or generate course script
- Break down script into recording units (lines or segments)
- Identify key points and emphasis areas
- Prepare recording structure and flow

### Phase 2: Set Recording Parameters and Prompts
- Configure recording settings (sample rate, format, quality)
- Set up tone and style guidelines
- Generate tone suggestions for each line/segment
- Prepare prompts and guidance for recording
- Set up quality check criteria

### Phase 3: Guide Recording Process
- Provide tone and style guidance for each segment
- Use `voice_recording.play_demo` to play example audio (if available)
- Guide user through recording each line using `voice_recording.record_line`
- Provide real-time feedback and suggestions
- Track recording progress and completion

### Phase 4: Check Recording Quality
- Review recorded audio quality
- Use `voice_recording.transcribe` to verify content accuracy
- Check tone and pacing consistency
- Identify segments that need re-recording
- Validate audio meets quality standards

### Phase 5: Generate Recording Report
- Compile all recording information
- Use `voice_recording.merge_recordings` to combine segments if needed
- Generate recording report with:
  - Recording summary and statistics
  - Quality assessment
  - Completion status
  - Recommendations for improvements
  - Next steps and follow-up actions
- Provide final audio files and transcripts

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "course creator", emphasize educational effectiveness and clarity
- **Work Style**: If prefers "structured", provide detailed recording checklists
- **Detail Level**: If prefers "high", include more granular quality checks

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Complete course production"), explicitly reference it in responses:
> "Since you're working towards 'Complete course production', I'll guide you through recording to ensure quality and consistency..."

## Integration with Other Playbooks

This playbook can work in conjunction with:
- `content_editing` - Edit and refine course scripts before recording
- `publishing_workflow` - Prepare recorded content for publishing

## Integration with Voice Recording

This playbook deeply integrates with Voice Recording capability pack:

**Core Tools Used**:
- `voice_recording.record_line` - Record individual lines or segments
- `voice_recording.play_demo` - Play example audio for guidance
- `voice_recording.transcribe` - Transcribe recordings for verification
- `voice_recording.merge_recordings` - Combine multiple recordings

**Optional Tools**:
- `voice_recording.synthesize` - Generate TTS demo audio (if needed)

**Workflow**:
1. Guide user through recording process line by line
2. Provide tone and style suggestions
3. Play demo audio to show desired style
4. Record each segment with quality checks
5. Transcribe and verify content
6. Merge recordings into final audio file

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存錄製筆記
**必須**使用 `sandbox.write_file` 工具保存錄製筆記（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `recording_notes.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的錄製過程記錄，包含參數設定、指導說明和品質檢查結果
- 格式: Markdown 格式

#### 步驟 6.2: 保存轉錄稿（如已生成）
如果已生成轉錄稿，保存到：

- 文件路徑: `transcript.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的音頻轉錄稿
- 格式: Markdown 格式

## Success Criteria
- Course outline and script are prepared
- Recording parameters are set
- Recording process is guided successfully
- Recording quality is checked and validated
- Comprehensive recording report is generated
- User has high-quality recorded course content
