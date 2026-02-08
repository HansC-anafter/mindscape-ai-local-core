---
playbook_code: style_system_gen
version: 1.0.0
capability_code: web_generation
name: Style System Generation
description: |
  Generate complete style system from theme configuration in site_spec.yaml, including CSS variables, Tailwind configuration, and global styles.
  This is the second step in the complete website generation workflow, providing unified style foundation for subsequent component generation.
tags:
  - web
  - styling
  - css
  - tailwind
  - design-system

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
icon: 🎨
---

# Style System Generation - SOP

## Goal

Generate complete style system from `theme` configuration in `spec/site_spec.yaml`, including:
- CSS variables file (`styles/variables.css`)
- Tailwind configuration file (`tailwind.config.js`)
- Global styles file (`styles/global.css`)

Output to Project Sandbox `styles/` directory.

**Workflow Description**:
- This is the **second step** in the complete website generation workflow: generate style system
- Must execute after `site_spec_generation` playbook
- Generated style system will be used by subsequent component generation and page assembly

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for Active web_page or website Project
- Check if `project_id` exists in execution context
- If yes, confirm project type is `web_page` or `website`
- If no, prompt user to create project first

#### Step 0.2: Get Project Sandbox Path
- Use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- Ensure `styles/` directory exists

#### Step 0.3: Read Site Specification Document
- Read `spec/site_spec.yaml` (generated from `site_spec_generation` playbook)
- If not exists, prompt user to execute `site_spec_generation` playbook first
- Parse site specification, extract `theme` configuration

### Phase 1: Parse Theme Configuration

#### Step 1.1: Read site_spec.yaml
**Must** use `filesystem_read_file` tool to read site specification document:

- **File Path**: `spec/site_spec.yaml` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/spec/site_spec.yaml`

#### Step 1.2: Extract Theme Configuration
Extract `theme` block from `site_spec.yaml`:
- `theme.colors`: Color scheme (primary, secondary, accent, neutral, semantic)
- `theme.typography`: Typography configuration (heading_font, body_font, accent_font, type_scale, line_heights)
- `theme.spacing`: Spacing scale
- `theme.breakpoints`: Responsive breakpoints

#### Step 1.3: Validate Theme Configuration
Ensure all required theme configurations exist:
- If some configurations are missing, use reasonable defaults
- Record used defaults for user review

### Phase 2: Generate CSS Variables File

#### Step 2.1: Build CSS Variables Structure
Build CSS variables based on theme configuration:

```css
:root {
  /* Colors */
  --color-primary: {theme.colors.primary};
  --color-secondary: {theme.colors.secondary};
  --color-accent: {theme.colors.accent};
  --color-neutral-{n}: {theme.colors.neutral[n]};
  --color-success: {theme.colors.semantic.success};
  --color-warning: {theme.colors.semantic.warning};
  --color-error: {theme.colors.semantic.error};
  --color-info: {theme.colors.semantic.info};

  /* Typography */
  --font-heading: {theme.typography.heading_font};
  --font-body: {theme.typography.body_font};
  --font-accent: {theme.typography.accent_font};
  --font-size-h1: {theme.typography.type_scale.h1};
  --font-size-h2: {theme.typography.type_scale.h2};
  --font-size-h3: {theme.typography.type_scale.h3};
  --font-size-body: {theme.typography.type_scale.body};
  --line-height-h1: {theme.typography.line_heights.h1};
  --line-height-h2: {theme.typography.line_heights.h2};
  --line-height-body: {theme.typography.line_heights.body};

  /* Spacing */
  --spacing-{n}: {theme.spacing[n]}px;

  /* Breakpoints */
  --breakpoint-sm: {theme.breakpoints.sm};
  --breakpoint-md: {theme.breakpoints.md};
  --breakpoint-lg: {theme.breakpoints.lg};
  --breakpoint-xl: {theme.breakpoints.xl};
}
```

#### Step 2.2: Generate variables.css
**Must** use `filesystem_write_file` tool to save CSS variables file:

- **File Path**: `styles/variables.css` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/styles/variables.css`

### Phase 3: Generate Tailwind Configuration File

#### Step 3.1: Build Tailwind Configuration Structure
Build Tailwind configuration based on theme configuration:

```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./sections/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '{theme.colors.primary}',
        secondary: '{theme.colors.secondary}',
        accent: '{theme.colors.accent}',
        neutral: {
          // Generated from theme.colors.neutral
        },
        success: '{theme.colors.semantic.success}',
        warning: '{theme.colors.semantic.warning}',
        error: '{theme.colors.semantic.error}',
        info: '{theme.colors.semantic.info}',
      },
      fontFamily: {
        heading: ['{theme.typography.heading_font}', 'sans-serif'],
        body: ['{theme.typography.body_font}', 'sans-serif'],
        accent: ['{theme.typography.accent_font}', 'serif'],
      },
      fontSize: {
        h1: '{theme.typography.type_scale.h1}',
        h2: '{theme.typography.type_scale.h2}',
        h3: '{theme.typography.type_scale.h3}',
        body: '{theme.typography.type_scale.body}',
      },
      lineHeight: {
        h1: {theme.typography.line_heights.h1},
        h2: {theme.typography.line_heights.h2},
        body: {theme.typography.line_heights.body},
      },
      spacing: {
        // Generated from theme.spacing
      },
      screens: {
        sm: '{theme.breakpoints.sm}',
        md: '{theme.breakpoints.md}',
        lg: '{theme.breakpoints.lg}',
        xl: '{theme.breakpoints.xl}',
      },
    },
  },
  plugins: [],
}
```

#### Step 3.2: Generate tailwind.config.js
**Must** use `filesystem_write_file` tool to save Tailwind configuration file:

- **File Path**: `tailwind.config.js` (in Project Sandbox root)
- **Full Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/tailwind.config.js`

### Phase 4: Generate Global Styles File

#### Step 4.1: Build Global Styles Structure
Build global styles based on theme configuration:

```css
@import './variables.css';
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  * {
    @apply box-border;
  }

  html {
    @apply scroll-smooth;
  }

  body {
    @apply font-body text-body antialiased;
    font-family: var(--font-body);
    font-size: var(--font-size-body);
    line-height: var(--line-height-body);
    color: var(--color-neutral-900);
    background-color: var(--color-neutral-50);
  }

  h1, h2, h3, h4, h5, h6 {
    @apply font-heading font-bold;
    font-family: var(--font-heading);
  }

  h1 {
    font-size: var(--font-size-h1);
    line-height: var(--line-height-h1);
  }

  h2 {
    font-size: var(--font-size-h2);
    line-height: var(--line-height-h2);
  }

  h3 {
    font-size: var(--font-size-h3);
    line-height: var(--line-height-h3);
  }

  a {
    @apply text-primary hover:text-accent transition-colors;
  }

  button {
    @apply transition-all;
  }
}

@layer components {
  .container-custom {
    @apply mx-auto px-4;
    max-width: 1200px;
  }

  .section-padding {
    @apply py-16 md:py-24;
  }
}

@layer utilities {
  .text-balance {
    text-wrap: balance;
  }
}
```

#### Step 4.2: Generate global.css
**Must** use `filesystem_write_file` tool to save global styles file:

- **File Path**: `styles/global.css` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/styles/global.css`

### Phase 5: Generate Style Documentation (Optional)

#### Step 5.1: Generate Style Usage Guide
**Optional** generate style usage documentation:

- **File Path**: `styles/README.md`
- **Content**:
  - Color system explanation
  - Typography system explanation
  - Spacing system explanation
  - Responsive breakpoints explanation
  - Usage examples

### Phase 6: Validate Generated Style Files

#### Step 6.1: Validate CSS Syntax
- Check if CSS variables file syntax is correct
- Check if global styles file syntax is correct

#### Step 6.2: Validate Tailwind Configuration
- Check if Tailwind configuration format is correct
- Ensure all colors, fonts, spacing are correctly mapped

#### Step 6.3: Check File Completeness
- Confirm all required files are generated
- Confirm file paths are correct

### Phase 7: Register Artifacts

#### Step 7.1: Register Style File Artifacts
**Must** use `artifact_registry.register_artifact` to register output artifacts:

1. **CSS Variables File**:
   - **artifact_id**: `style_variables`
   - **artifact_type**: `css`
   - **path**: `styles/variables.css`

2. **Tailwind Configuration**:
   - **artifact_id**: `tailwind_config`
   - **artifact_type**: `config`
   - **path**: `tailwind.config.js`

3. **Global Styles**:
   - **artifact_id**: `global_styles`
   - **artifact_type**: `css`
   - **path**: `styles/global.css`

### Phase 8: Execution Record Saving

#### Step 8.1: Save Conversation History
**Must** use `filesystem_write_file` tool to save complete conversation history:

- File path: `artifacts/style_system_gen/{{execution_id}}/conversation_history.json`
- Content: Complete conversation history (all user and assistant messages)
- Format: JSON format with timestamps and role information

#### Step 8.2: Save Execution Summary
**Must** use `filesystem_write_file` tool to save execution summary:

- File path: `artifacts/style_system_gen/{{execution_id}}/execution_summary.md`
- Content:
  - Execution time
  - Execution ID
  - Playbook name
  - Read site_spec.yaml path
  - Generated style files list
  - Default values used (if any)
  - Validation results

## Personalization

Based on user's Mindscape profile:
- **Technical Level**: If "advanced", include more customization options and advanced configuration
- **Detail Level**: If preference is "high", provide more detailed style explanations and comments
- **Work Style**: If preference is "structured", provide clearer style organization structure

## Integration with Long-term Intentions

If user has related active intentions (e.g., "Build brand website"), explicitly reference:
> "Since you are working on 'Build brand website', I will generate a consistent style system based on your brand identity..."

## Success Criteria

- CSS variables file generated to `styles/variables.css`
- Tailwind configuration file generated to `tailwind.config.js`
- Global styles file generated to `styles/global.css`
- All style files have correct syntax
- All theme configurations are correctly mapped to style system
- Artifacts correctly registered
- Style system can seamlessly integrate with subsequent component generation and page assembly

## Notes

- **Project Context**: Must execute in web_page or website project context
- **Dependencies**: Must execute `site_spec_generation` playbook first
- **Sandbox Path**: Ensure using Project Sandbox path, not artifacts path
- **Backward Compatibility**: If no project context, can downgrade to artifacts path (but will prompt user)
- **Default Value Handling**: If theme configuration is incomplete, use reasonable defaults and record

## Related Documentation

- **Schema Definition**: `capabilities/web_generation/schema/site_spec_schema.py`
- **Site Specification Generation**: `capabilities/web_generation/playbooks/en/site_spec_generation.md`
- **Complete Website Generation Workflow**: `capabilities/web_generation/docs/complete-pipeline-workflow.md`

