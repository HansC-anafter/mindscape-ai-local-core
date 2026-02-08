---
playbook_code: page_sections
version: 1.0.0
capability_code: web_generation
name: Page Sections Generation
description: Read page specification document, generate React components for each section
tags:
  - web
  - code-generation
  - react
  - frontend

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - filesystem_write_file
  - filesystem_read_file

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🧩
---

# Page Sections Generation - SOP

## Goal
Read `spec/page.md` page specification document, generate React components for each section, output to Project Sandbox's `sections/` directory.

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for Active web_page Project
- Check if `project_id` exists in execution context
- If yes, confirm project type is `web_page`
- If no, prompt user to create web_page project first

#### Step 0.2: Get Project Sandbox Path
- Use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/web_page/{project_id}/`
- Ensure `sections/` directory exists

#### Step 0.3: Read Page Specification Document
- Read `spec/page.md` (generated from `page_outline` playbook)
- If not exists, prompt user to execute `page_outline` playbook first
- Parse page specification, extract sections list

### Phase 1: Parse Page Specification

#### Step 1.1: Read `spec/page.md`
**Must** use `filesystem_read_file` tool to read page specification document:

- **File Path**: `spec/page.md` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/web_page/{project_id}/spec/page.md`

#### Step 1.2: Parse Sections List
Extract from `page.md`:
- List of all sections (About, Features, Content, Contact, etc.)
- Content points for each section
- Layout method for each section
- Visual element requirements for each section

#### Step 1.3: Extract Style Guidelines
Extract from `page.md`:
- Color scheme (primary, secondary, accent colors)
- Font suggestions
- Visual style
- Interaction design requirements

### Phase 2: Generate Section Components

#### Step 2.1: About Section Component
If page specification includes About Section:

- **Component Name**: `About.tsx`
- **Output Path**: `sections/About.tsx`
- **Component Content**:
  - Generate based on About Section content points from page.md
  - Use unified style guidelines (extracted from page.md)
  - Implement responsive design
  - Include appropriate visual elements (images, icons, etc.)

**Component Structure Example**:
```typescript
import React from 'react'

interface AboutProps {
  // Props based on page.md specification
}

export default function About({ ...props }: AboutProps) {
  return (
    <section className="about-section">
      {/* Content based on page.md */}
    </section>
  )
}
```

#### Step 2.2: Features Section Component
If page specification includes Features Section:

- **Component Name**: `Features.tsx`
- **Output Path**: `sections/Features.tsx`
- **Component Content**:
  - Generate based on feature items list from page.md
  - Use specified display method (cards, list, timeline, etc.)
  - Implement interactive effects (if specified)
  - Use unified style guidelines

#### Step 2.3: Content Section Component
If page specification includes Content Section:

- **Component Name**: `Content.tsx`
- **Output Path**: `sections/Content.tsx`
- **Component Content**:
  - Generate based on content structure from page.md
  - Support specified content types (articles, images, videos, etc.)
  - Implement appropriate display method

#### Step 2.4: Contact Section Component
If page specification includes Contact Section:

- **Component Name**: `Contact.tsx`
- **Output Path**: `sections/Contact.tsx`
- **Component Content**:
  - Generate based on contact information from page.md
  - Implement form (if specified)
  - Include social media links (if specified)
  - Use unified style guidelines

#### Step 2.5: Other Sections
Based on other sections defined in page.md, generate corresponding components:
- One component file per section
- Component names use PascalCase
- Ensure all components use unified style guidelines

### Phase 3: Style Consistency Handling

#### Step 3.1: Create Shared Style File (Optional)
If needed, create shared style file:

- **File Path**: `sections/styles.ts` or `sections/styles.css`
- **Content**: Unified style definitions (colors, fonts, spacing, etc.)
- All section components reference this file

#### Step 3.2: Ensure Component Style Consistency
- All components use same color scheme
- All components use same fonts
- All components use same spacing and layout rules
- All components implement responsive design

### Phase 4: Component Output and Saving

#### Step 4.1: Save All Section Components
**Must** use `filesystem_write_file` tool to save each section component:

- **About.tsx**: `sections/About.tsx`
- **Features.tsx**: `sections/Features.tsx`
- **Content.tsx**: `sections/Content.tsx`
- **Contact.tsx**: `sections/Contact.tsx`
- Other sections...

#### Step 4.2: Register Artifacts
**Must** use `artifact_registry.register_artifact` to register output artifacts:

- **artifact_id**: `sections`
- **artifact_type**: `react_components`
- **path**: `sections/`
- **metadata**:
  - `components`: Component list (["About.tsx", "Features.tsx", ...])
  - `count`: Component count
  - `created_at`: Creation time

### Phase 5: Execution Record Saving

#### Step 5.1: Save Conversation History
**Must** use `filesystem_write_file` tool to save complete conversation history:

- File path: `artifacts/page_sections/{{execution_id}}/conversation_history.json`
- Content: Complete conversation history (including all user and assistant messages)
- Format: JSON format with timestamps and role information

#### Step 5.2: Save Execution Summary
**Must** use `filesystem_write_file` tool to save execution summary:

- File path: `artifacts/page_sections/{{execution_id}}/execution_summary.md`
- Content:
  - Execution time
  - Execution ID
  - Playbook name
  - Read page specification document path
  - Generated component list
  - Execution result summary

## Personalization

Based on user's Mindscape Profile:
- **Technical Level**: If "advanced", include more technical details and custom options
- **Detail Level**: If "high", provide more detailed component implementation
- **Work Style**: If "structured", provide clearer component structure

## Integration with Long-term Intents

If user has relevant Active Intent (e.g., "Build Company Landing Page"), explicitly reference:
> "Since you're working on 'Build Company Landing Page', I'll generate all necessary section components based on the page specification..."

## Success Criteria

- All section components generated to Project Sandbox's `sections/` directory
- Components generated based on planning in `spec/page.md`
- All components use unified style guidelines
- Components implement responsive design
- Artifacts correctly registered
- Components can be used directly in React projects

## Notes

- **Dependencies**: Must execute `page_outline` playbook first to generate `spec/page.md`
- **Project Context**: Must execute in web_page project context
- **Style Consistency**: Ensure all components use same style guidelines (extracted from page.md)
- **Component Naming**: Use PascalCase, consistent with React conventions
- **Responsive Design**: All components should implement responsive design

