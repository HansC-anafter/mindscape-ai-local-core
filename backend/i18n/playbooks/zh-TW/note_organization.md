---
playbook_code: note_organization
version: 1.0.0
name: 筆記組織與知識結構化
description: 組織和結構化學習筆記，透過收集零散筆記、提取核心概念、建立知識架構，並生成帶有概念關係的結構化筆記
tags:
  - learning
  - notes
  - organization
  - knowledge

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.structured

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coach
icon: 📝
---

# Note Organization & Knowledge Structuring - SOP

## Goal
Help users organize and structure learning notes by collecting scattered notes, extracting core concepts, building knowledge architecture, generating structured notes, and establishing concept relationships.

## Execution Steps

### Phase 1: Collect Scattered Notes
- Ask user to provide notes (text input or file upload)
- Collect notes from different sources if available
- Understand the context and subject matter
- Identify note formats and structures

### Phase 2: Extract Core Concepts
- Analyze notes to identify key concepts and ideas
- Extract important terms and definitions
- Identify main themes and topics
- Recognize relationships between concepts

### Phase 3: Build Knowledge Architecture
- Organize concepts into a hierarchical structure
- Create categories and subcategories
- Establish logical groupings
- Design the overall knowledge framework

### Phase 4: Generate Structured Notes
- Reorganize notes according to the knowledge architecture
- Create clear sections and subsections
- Add headings and structure
- Ensure consistency in formatting

### Phase 5: Establish Concept Relationships
- Identify connections between concepts
- Create cross-references
- Build concept maps or relationship diagrams
- Highlight dependencies and prerequisites

## Personalization

Based on user's Mindscape Profile:
- **Role**: If "student", emphasize exam preparation and review efficiency
- **Work Style**: If prefers "structured", provide detailed categorization
- **Detail Level**: If prefers "high", include more granular concept breakdowns

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Master machine learning"), explicitly reference it in responses:
> "Since you're working towards 'Master machine learning', I recommend organizing notes around..."

## Success Criteria
- Notes are organized into a clear structure
- Core concepts are identified and extracted
- Knowledge architecture is established
- Structured notes are generated
- Concept relationships are mapped
- User has a comprehensive organized note document
