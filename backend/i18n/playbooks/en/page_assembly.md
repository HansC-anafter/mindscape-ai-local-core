---
playbook_code: page_assembly
version: 1.0.0
capability_code: web_generation
name: Page Assembly
description: Integrate all components (hero + sections), generate complete page component
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
icon: 🔧
---

# Page Assembly - SOP

## Goal
Read all components (hero + sections) and page specification, integrate into complete page component, output to Project Sandbox's `pages/index.tsx`.

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for Active web_page Project
- Check if `project_id` exists in execution context
- If yes, confirm project type is `web_page`
- If no, prompt user to create web_page project first

#### Step 0.2: Get Project Sandbox Path
- Use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/web_page/{project_id}/`
- Ensure `pages/` directory exists

#### Step 0.3: Check Dependent Artifacts
Check if following artifacts exist:
- `page_spec` - Page specification document (`spec/page.md`)
- `hero_component` - Hero component (`hero/Hero.tsx`)
- `sections` - Sections components (`sections/` directory)

If any doesn't exist, prompt user to execute corresponding playbook first.

### Phase 1: Read All Components and Specification

#### Step 1.1: Read Page Specification Document
**Must** use `filesystem_read_file` tool to read:

- **File Path**: `spec/page.md`
- **Purpose**: Understand page structure, style guidelines, layout requirements

#### Step 1.2: Read Hero Component
**Must** use `filesystem_read_file` tool to read:

- **File Path**: `hero/Hero.tsx`
- **Purpose**: Understand Hero component structure and props

#### Step 1.3: Read All Section Components
**Must** use `filesystem_read_file` tool to read:

- **File Path**: `sections/About.tsx`, `sections/Features.tsx`, etc.
- **Purpose**: Understand all section component structures

#### Step 1.4: Check Component Dependencies
- Check dependencies used by all components (React, style libraries, etc.)
- Ensure dependencies are consistent
- Identify shared styles or utility functions needed

### Phase 2: Design Page Structure

#### Step 2.1: Plan Page Layout
Based on layout planning in `spec/page.md`:
- Determine overall page structure
- Plan component arrangement order
- Determine responsive design breakpoints

#### Step 2.2: Design Component Integration Method
- Hero component position and integration method
- Sections arrangement order
- Spacing and layout between components
- Navigation structure (if specified)

#### Step 2.3: Design Style Integration
- Unify styles for all components
- Ensure color scheme consistency
- Ensure font consistency
- Handle global styles (if needed)

### Phase 3: Generate Complete Page Component

#### Step 3.1: Create Main Page Component
Generate `pages/index.tsx`, including:

- **Import Statements**:
  - Import Hero component
  - Import all Section components
  - Import necessary styles and utilities

- **Component Structure**:
```typescript
import React from 'react'
import Hero from '../hero/Hero'
import About from '../sections/About'
import Features from '../sections/Features'
import Content from '../sections/Content'
import Contact from '../sections/Contact'
// ... other imports

export default function HomePage() {
  return (
    <div className="page-container">
      <Hero />
      <About />
      <Features />
      <Content />
      <Contact />
      {/* Footer if specified */}
    </div>
  )
}
```

#### Step 3.2: Implement Responsive Design
- Based on responsive design requirements in `spec/page.md`
- Implement mobile, tablet, desktop adaptations
- Use CSS Media Queries or Tailwind responsive classes

#### Step 3.3: Integrate Styles
- Ensure all components use unified style guidelines
- Handle global styles (if needed)
- Create shared style files (if needed)

#### Step 3.4: Handle Interactions and Animations
- Based on interaction design requirements in `spec/page.md`
- Implement scroll-triggered animations (if needed)
- Implement page transition effects (if needed)

### Phase 4: Optimization and Test Preparation

#### Step 4.1: Code Optimization
- Ensure code follows React best practices
- Optimize component performance (use React.memo, useMemo, etc.)
- Ensure no TypeScript errors
- Ensure no ESLint warnings

#### Step 4.2: Documentation and Comments
- Add appropriate code comments
- Ensure component props have clear type definitions
- Add usage instructions (if needed)

#### Step 4.3: Dependency Check
- List all required npm dependencies
- Ensure dependency versions are compatible
- Provide installation instructions

### Phase 5: Component Output and Saving

#### Step 5.1: Save Complete Page Component
**Must** use `filesystem_write_file` tool to save:

- **File Path**: `pages/index.tsx` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/web_page/{project_id}/pages/index.tsx`
- **Content**: Complete page component code

#### Step 5.2: Save Shared Style Files (if needed)
If shared style files were created:

- **File Path**: `styles/global.css` or `styles/theme.ts`
- **Content**: Unified style definitions

#### Step 5.3: Save Dependency List
**Must** use `filesystem_write_file` tool to save:

- **File Path**: `package.json` or `dependencies.md`
- **Content**: List of all required npm dependencies

#### Step 5.4: Register Artifact
**Must** use `artifact_registry.register_artifact` to register output artifact:

- **artifact_id**: `complete_page`
- **artifact_type**: `react_component`
- **path**: `pages/index.tsx`
- **metadata**:
  - `component_name`: `HomePage`
  - `framework`: `react`
  - `dependencies`: Dependency list
  - `created_at`: Creation time

### Phase 6: Execution Record Saving

#### Step 6.1: Save Conversation History
**Must** use `filesystem_write_file` tool to save complete conversation history:

- File path: `artifacts/page_assembly/{{execution_id}}/conversation_history.json`
- Content: Complete conversation history (including all user and assistant messages)
- Format: JSON format with timestamps and role information

#### Step 6.2: Save Execution Summary
**Must** use `filesystem_write_file` tool to save execution summary:

- File path: `artifacts/page_assembly/{{execution_id}}/execution_summary.md`
- Content:
  - Execution time
  - Execution ID
  - Playbook name
  - Integrated component list
  - Generated complete page component path
  - Dependency list
  - Execution result summary

## Personalization

Based on user's Mindscape Profile:
- **Technical Level**: If "advanced", include more optimizations and custom options
- **Detail Level**: If "high", provide more detailed code comments and explanations
- **Work Style**: If "structured", provide clearer component structure and organization

## Integration with Long-term Intents

If user has relevant Active Intent (e.g., "Build Company Landing Page"), explicitly reference:
> "Since you're working on 'Build Company Landing Page', I've integrated all components into a complete page that can be deployed directly..."

## Success Criteria

- Complete page component generated to Project Sandbox's `pages/index.tsx`
- All components (hero + sections) correctly integrated
- Styles unified and consistent
- Responsive design implemented
- Code has no errors and can be used directly
- Artifact correctly registered
- Dependency list provided

## Notes

- **Dependencies**: Must execute `page_outline`, `threejs_hero_landing`, `page_sections` playbooks first
- **Project Context**: Must execute in web_page project context
- **Style Consistency**: Ensure all components use unified style guidelines
- **Performance Optimization**: Ensure components perform well, no unnecessary re-renders
- **Maintainability**: Ensure code structure is clear, easy to maintain and extend

