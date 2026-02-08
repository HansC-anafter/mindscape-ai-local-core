---
playbook_code: page_outline
version: 1.0.0
capability_code: web_generation
name: Page Structure Planning
description: Analyze user requirements, plan page structure (sections, layout, content direction), generate page specification document
tags:
  - web
  - planning
  - design
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

entry_agent_type: planner
icon: 📋
---

# Page Structure Planning - SOP

## Goal
Analyze user requirements, plan page structure (sections, layout, content direction), generate `spec/page.md` page specification document to Project Sandbox.

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for Active web_page Project
- Check if `project_id` exists in execution context
- If yes, confirm project type is `web_page`
- If no, prompt user to create web_page project first

#### Step 0.2: Get Project Sandbox Path
- Use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/web_page/{project_id}/`
- Ensure `spec/` directory exists

### Phase 1: Requirements Gathering

#### Step 1.1: Page Theme and Goals
- **Theme**: Ask for page theme or topic (e.g., "Urban Awareness", "Product Introduction", "Personal Portfolio")
- **Goals**: Understand page's main goals (showcase, conversion, education, brand image, etc.)
- **Target Audience**: Identify target audience (general users, professionals, potential customers, etc.)

#### Step 1.2: Content Direction
- **Core Message**: Identify core messages to convey
- **Content Type**: Determine content types (text, images, videos, interactive elements, etc.)
- **Style Preferences**: Understand design style preferences (modern, minimalist, retro, tech, etc.)

#### Step 1.3: Functional Requirements
- **Interaction Requirements**: Whether interactive elements are needed (forms, animations, 3D effects, etc.)
- **Responsive Requirements**: Mobile device adaptation requirements
- **Performance Requirements**: Performance constraints and target devices

### Phase 2: Page Structure Design

#### Step 2.1: Hero Section Planning
- **Hero Type**: Determine hero section type (Three.js interactive, static image, video background, etc.)
- **Hero Content**: Plan hero section's main content (title, subtitle, CTA button, etc.)
- **Hero Style**: Define hero section's visual style and animation effects

#### Step 2.2: Sections Planning
Plan each section for the page:

- **About Section**
  - Content points
  - Visual elements (images, icons, etc.)
  - Layout method (single column, double column, grid, etc.)

- **Features Section**
  - Feature items list
  - Display method (cards, list, timeline, etc.)
  - Interactive effects

- **Content Section**
  - Content type (articles, images, videos, etc.)
  - Content structure
  - Display method

- **Contact Section**
  - Contact information
  - Form design
  - Social media links

- **Footer**
  - Footer content
  - Link structure
  - Copyright information

#### Step 2.3: Navigation and Layout
- **Navigation Structure**: Plan navigation menu structure
- **Page Layout**: Determine overall layout method (single page, multi-page, sections, etc.)
- **Responsive Design**: Plan layout adaptation for different screen sizes

### Phase 3: Content Outline Planning

#### Step 3.1: Section Content Points
Plan specific content points for each section:

- **Hero Section**
  - Main title
  - Subtitle
  - CTA button text
  - Background element description

- **About Section**
  - About content points (3-5 key points)
  - Visual element requirements

- **Features Section**
  - Feature items list (title and description for each item)
  - Icon or image requirements

- **Content Section**
  - Content paragraph structure
  - Image or video requirements

- **Contact Section**
  - Contact information
  - Form fields

#### Step 3.2: Content Priority
- Determine content priority (which are core messages, which are secondary information)
- Plan content display order

### Phase 4: Style and Interaction Design Recommendations

#### Step 4.1: Visual Style Definition
- **Color Scheme**: Define primary colors, secondary colors, accent colors
- **Font Selection**: Suggest font families and font sizes
- **Visual Elements**: Icon style, image style, animation style

#### Step 4.2: Interaction Design
- **Animation Effects**: Plan page animation effects (scroll triggers, hover effects, etc.)
- **Interactive Elements**: Define interactive element behaviors (buttons, forms, navigation, etc.)
- **User Experience**: Ensure good user experience flow

### Phase 5: Generate Page Specification Document

#### Step 5.1: Generate `spec/page.md`
**Must** use `filesystem_write_file` tool to save page specification document:

- **File Path**: `spec/page.md` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/web_page/{project_id}/spec/page.md`

**Document Structure**:
```markdown
# Page Specification: {Page Title}

## Page Information
- **Theme**: {Theme}
- **Goals**: {Goals}
- **Target Audience**: {Target Audience}

## Hero Section
- **Type**: {Hero Type}
- **Content**:
  - Main Title: {Main Title}
  - Subtitle: {Subtitle}
  - CTA: {CTA Text}
- **Style**: {Style Description}

## Sections Planning

### About Section
- **Content Points**:
  - {Point 1}
  - {Point 2}
- **Layout**: {Layout Method}
- **Visual Elements**: {Visual Element Requirements}

### Features Section
- **Feature Items**:
  - {Item 1}: {Description}
  - {Item 2}: {Description}
- **Display Method**: {Display Method}

### Content Section
- **Content Structure**: {Content Structure}
- **Content Type**: {Content Type}

### Contact Section
- **Contact Method**: {Contact Method}
- **Form Fields**: {Form Fields}

## Style Guidelines
- **Color Scheme**:
  - Primary: {Primary Color}
  - Secondary: {Secondary Color}
  - Accent: {Accent Color}
- **Font**: {Font Suggestion}
- **Visual Style**: {Visual Style}

## Interaction Design
- **Animation Effects**: {Animation Effects}
- **Interactive Elements**: {Interactive Elements}
```

#### Step 5.2: Register Artifact
**Must** use `artifact_registry.register_artifact` to register output artifact:

- **artifact_id**: `page_spec`
- **artifact_type**: `markdown`
- **path**: `spec/page.md`
- **metadata**:
  - `page_title`: Page title
  - `sections`: Sections list
  - `created_at`: Creation time

### Phase 6: Execution Record Saving

#### Step 6.1: Save Conversation History
**Must** use `filesystem_write_file` tool to save complete conversation history:

- File path: `artifacts/page_outline/{{execution_id}}/conversation_history.json`
- Content: Complete conversation history (including all user and assistant messages)
- Format: JSON format with timestamps and role information

#### Step 6.2: Save Execution Summary
**Must** use `filesystem_write_file` tool to save execution summary:

- File path: `artifacts/page_outline/{{execution_id}}/execution_summary.md`
- Content:
  - Execution time
  - Execution ID
  - Playbook name
  - Main input parameters (page theme, goals, content direction, etc.)
  - Execution result summary
  - Generated page specification document path

## Personalization

Based on user's Mindscape Profile:
- **Technical Level**: If "advanced", include more technical details and custom options
- **Detail Level**: If "high", provide more detailed planning and recommendations
- **Work Style**: If "structured", provide clearer structure and steps

## Integration with Long-term Intents

If user has relevant Active Intent (e.g., "Build Company Landing Page"), explicitly reference:
> "Since you're working on 'Build Company Landing Page', I'll focus on creating a page structure that aligns with your brand identity and conversion goals..."

## Success Criteria

- Page specification document generated to Project Sandbox's `spec/page.md`
- Document contains complete page structure planning
- All sections have clear content points
- Style and interaction design recommendations included
- Artifact correctly registered
- Document format is clear and easy for subsequent playbooks to use

## Notes

- **Project Context**: Must execute in web_page project context
- **Sandbox Path**: Ensure using Project Sandbox path, not artifacts path
- **Document Format**: Use Markdown format, ensure clear structure
- **Backward Compatibility**: If no project context, can fallback to artifacts path (but will prompt user)

