---
playbook_code: note_organization
version: 1.0.0
name: Note Organization & Knowledge Structuring
description: Organize and structure learning notes by collecting scattered notes, extracting core concepts, building knowledge architecture, and generating structured notes with concept relationships
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
  - sandbox.write_file
  - sandbox.read_file
  - filesystem_write_file
  - filesystem_read_file
  - core_llm.structured_extract

language_strategy: model_native
locale: en
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

### Phase 6: File Generation and Saving

#### Step 6.1: Save Organized Notes
**Must** use `sandbox.write_file` tool to save organized notes (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `organized_notes.md` (relative path, relative to sandbox root)
- Content: Complete structured notes, including all sections, concepts, and relationships
- Format: Markdown format

#### Step 6.2: Save Knowledge Structure
**Must** use `sandbox.write_file` tool to save knowledge structure (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `knowledge_structure.md` (relative path, relative to sandbox root)
- Content: Knowledge architecture and concept relationship diagram
- Format: Markdown format

## Success Criteria
- Notes are organized into a clear structure
- Core concepts are identified and extracted
- Knowledge architecture is established
- Structured notes are generated
- Concept relationships are mapped
- User has a comprehensive organized note document

