---
playbook_code: site_spec_generation
version: 1.0.0
capability_code: web_generation
name: Site Specification Generation
description: |
  Generate complete site specification document (site_spec.yaml). Supports generation from user requirements or conversion from existing site_structure.yaml.
  This is the first step in the complete website generation workflow, defining multi-page structure, navigation, theme configuration, and component requirements.
tags:
  - web
  - planning
  - site-spec
  - multi-page
  - website

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
icon: 📐
---

# Site Specification Generation - SOP

## Goal

Generate complete site specification document `spec/site_spec.yaml` to Project Sandbox. This specification defines multi-page structure, navigation, theme configuration, and component requirements, serving as the foundation for complete website generation.

**Workflow Description**:
- This is the **first step** in the complete website generation workflow: generate site specification
- Supports two modes:
  1. **Generate from requirements**: Generate complete specification from user input
  2. **Upgrade from existing specification**: Convert from `site_structure.yaml` and supplement with complete specification

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for Active web_page or website Project
- Check if `project_id` exists in execution context
- If yes, confirm project type is `web_page` or `website`
- If no, prompt user to create project first

#### Step 0.2: Get Project Sandbox Path
- Use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- Ensure `spec/` directory exists

#### Step 0.3: Check Existing Specification Files
- Check if `spec/site_structure.yaml` exists (from obsidian_to_site_spec)
- Check if `spec/page.md` exists (from page_outline, single page specification)
- Determine generation mode based on existing files

### Phase 1: Determine Generation Mode

#### Step 1.1: Mode Selection
Select generation mode based on existing files:

**Mode A: Upgrade from site_structure.yaml**
- If `spec/site_structure.yaml` exists
- Read existing structure
- Supplement theme configuration and component requirements
- Convert to complete `site_spec.yaml`

**Mode B: Generate from User Requirements**
- If no existing specification files
- Collect requirements from user input
- Generate complete specification

**Mode C: Expand from page.md**
- If `spec/page.md` exists (single page specification)
- Ask user if they need to expand to multi-page website
- If yes, collect multi-page requirements and generate complete specification

### Phase 2: Requirement Collection (Mode B or C)

#### Step 2.1: Site Basic Information
- **Site Title**: Ask for site title
- **Site Description**: Ask for site description and goals
- **Base URL**: Determine site base path (e.g., `/books/2025`)
- **Metadata**: Collect author, keywords, and other metadata

#### Step 2.2: Page Planning
- **Number of Pages**: Determine how many pages are needed
- **Page Types**: Type of each page (intro, chapter, section, landing, custom)
- **Page Structure**: Sections included in each page
- **Page Routes**: Determine route path for each page

#### Step 2.3: Navigation Planning
- **Top Navigation**: Top navigation items
- **Sidebar Navigation**: Sidebar navigation (if any)
- **Footer Navigation**: Footer navigation (if any)
- **Navigation Hierarchy**: Determine navigation hierarchy

#### Step 2.4: Theme Configuration Requirements
- **Color Preferences**: Ask for primary, secondary, accent color preferences
- **Font Preferences**: Ask for heading font, body font preferences
- **Style Preferences**: Modern, minimal, retro, tech, etc.
- **Responsive Requirements**: Breakpoint configuration requirements

#### Step 2.5: Component Requirements
- **Header**: Whether header is needed, what features are required
- **Footer**: Whether footer is needed, what content is required
- **Section Components**: What section components are needed (Features, CTA, About, etc.)
- **UI Components**: What basic UI components are needed

### Phase 3: Specification Generation

#### Step 3.1: Build SiteInfo
Build site basic information based on collected information:
```yaml
site:
  title: "{Site Title}"
  description: "{Site Description}"
  base_url: "{base_url}"
  metadata:
    author: "{Author}"
    keywords: ["{Keyword1}", "{Keyword2}"]
```

#### Step 3.2: Build PageSpec List
Create PageSpec for each page:
```yaml
pages:
  - route: "/"
    title: "Home"
    type: "intro"
    source: "{Source Path}"
    sections: ["hero", "about", "features"]
    status: "ready"
    metadata:
      seo_title: "{SEO Title}"
      seo_description: "{SEO Description}"
```

#### Step 3.3: Build NavigationSpec
Build navigation structure based on navigation planning:
```yaml
navigation:
  top:
    - label: "Home"
      route: "/"
    - label: "Chapters"
      route: "/chapters"
      children:
        - label: "Chapter 1"
          route: "/chapters/chapter-1"
  sidebar:
    - label: "Chapter 1"
      route: "/chapters/chapter-1"
      children:
        - label: "Section 1"
          route: "/chapters/chapter-1/section-1"
  footer:
    - label: "About"
      route: "/about"
```

#### Step 3.4: Build ThemeConfig
Build theme configuration based on theme requirements:
```yaml
theme:
  colors:
    primary: "{Primary Color}"
    secondary: "{Secondary Color}"
    accent: "{Accent Color}"
    neutral: ["{Neutral Color1}", "{Neutral Color2}"]
    semantic:
      success: "#10b981"
      warning: "#f59e0b"
      error: "#ef4444"
      info: "#3b82f6"
  typography:
    heading_font: "{Heading Font}"
    body_font: "{Body Font}"
    accent_font: "{Accent Font}"
    type_scale:
      h1: "3rem"
      h2: "2rem"
      h3: "1.5rem"
      body: "1rem"
    line_heights:
      h1: 1.2
      h2: 1.3
      body: 1.6
  spacing: [4, 8, 12, 16, 24, 32, 48, 64, 96]
  breakpoints:
    sm: "640px"
    md: "768px"
    lg: "1024px"
    xl: "1280px"
```

#### Step 3.5: Build ComponentRequirement List
Build component list based on component requirements:
```yaml
components:
  - component_id: "header"
    component_type: "header"
    required: true
    config:
      show_logo: true
      show_navigation: true
  - component_id: "footer"
    component_type: "footer"
    required: true
    config:
      show_copyright: true
  - component_id: "features_section"
    component_type: "section"
    required: false
    config:
      layout: "grid"
      columns: 3
```

### Phase 4: Convert from site_structure.yaml (Mode A)

#### Step 4.1: Read Existing Structure
- Read `spec/site_structure.yaml`
- Parse existing site, pages, navigation structure

#### Step 4.2: Convert SiteInfo
- Extract basic information from existing `site` block
- Supplement missing metadata

#### Step 4.3: Convert PageSpec
- Convert existing `pages` to PageSpec format
- Ensure all required fields have values
- Supplement missing sections and metadata

#### Step 4.4: Convert NavigationSpec
- Convert existing `navigation` to NavigationSpec format
- Ensure navigation items correspond to actual pages

#### Step 4.5: Supplement Theme Configuration
- If existing specification has no theme configuration, ask user or use defaults
- Generate ThemeConfig

#### Step 4.6: Supplement Component Requirements
- Derive required components based on page structure
- Generate ComponentRequirement list

### Phase 5: Schema Validation

#### Step 5.1: Validate with Pydantic Schema
**Must** use `capabilities.web_generation.schema.SiteSpec` to validate generated specification:

```python
from capabilities.web_generation.schema import SiteSpec
import yaml

# Read generated YAML
with open("spec/site_spec.yaml", "r") as f:
    data = yaml.safe_load(f)

# Validate
try:
    spec = SiteSpec(**data)
    spec.validate_routes()
    print("✅ Schema validation passed")
except Exception as e:
    print(f"❌ Schema validation failed: {e}")
    # Fix errors and regenerate
```

#### Step 5.2: Validate Route Uniqueness
- Ensure all page routes are unique
- Ensure navigation routes correspond to actual pages

#### Step 5.3: Validate Component Dependencies
- Ensure components marked as `required: true` have corresponding configuration
- Check component ID uniqueness

### Phase 6: Generate YAML File

#### Step 6.1: Generate site_spec.yaml
**Must** use `filesystem_write_file` tool to save site specification document:

- **File Path**: `spec/site_spec.yaml` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/spec/site_spec.yaml`

**YAML Format**:
```yaml
site:
  title: "{Site Title}"
  description: "{Site Description}"
  base_url: "{base_url}"
  metadata: {}

pages:
  - route: "/"
    title: "Home"
    type: "intro"
    source: "{Source Path}"
    sections: []
    status: "ready"
    metadata: {}

navigation:
  top: []
  sidebar: []
  footer: []

theme:
  colors:
    primary: "#0a0a2a"
    secondary: "#ffa0e0"
    accent: "#5C4DFF"
    neutral: []
    semantic: {}
  typography:
    heading_font: "Inter"
    body_font: "Inter"
    accent_font: null
    type_scale: {}
    line_heights: {}
  spacing: [4, 8, 12, 16, 24, 32, 48, 64, 96]
  breakpoints:
    sm: "640px"
    md: "768px"
    lg: "1024px"
    xl: "1280px"

components:
  - component_id: "header"
    component_type: "header"
    required: true
    config: {}
  - component_id: "footer"
    component_type: "footer"
    required: true
    config: {}

version: "1.0.0"
created_at: "{Timestamp}"
```

#### Step 6.2: Register Artifact
**Must** use `artifact_registry.register_artifact` to register output artifact:

- **artifact_id**: `site_spec`
- **artifact_type**: `yaml`
- **path**: `spec/site_spec.yaml`
- **metadata**:
  - `site_title`: Site title
  - `page_count`: Number of pages
  - `created_at`: Creation timestamp

### Phase 7: Execution Record Saving

#### Step 7.1: Save Conversation History
**Must** use `filesystem_write_file` tool to save complete conversation history:

- File path: `artifacts/site_spec_generation/{{execution_id}}/conversation_history.json`
- Content: Complete conversation history (all user and assistant messages)
- Format: JSON format with timestamps and role information

#### Step 7.2: Save Execution Summary
**Must** use `filesystem_write_file` tool to save execution summary:

- File path: `artifacts/site_spec_generation/{{execution_id}}/execution_summary.md`
- Content:
  - Execution time
  - Execution ID
  - Playbook name
  - Generation mode (from requirements/upgrade from existing specification)
  - Main input parameters
  - Execution result summary
  - Generated site specification document path
  - Schema validation results

## Personalization

Based on user's Mindscape profile:
- **Technical Level**: If "advanced", include more technical details and customization options
- **Detail Level**: If preference is "high", provide more detailed planning and suggestions
- **Work Style**: If preference is "structured", provide clearer structure and steps

## Integration with Long-term Intentions

If user has related active intentions (e.g., "Build company website"), explicitly reference:
> "Since you are working on 'Build company website', I will focus on creating a site specification that aligns with your brand identity and business goals..."

## Success Criteria

- Site specification document generated to Project Sandbox `spec/site_spec.yaml`
- Document conforms to `SiteSpec` schema definition
- Schema validation passed (route uniqueness, navigation consistency, etc.)
- All required fields have values
- Theme configuration complete
- Component requirements clear
- Artifact correctly registered
- Document format clear, easy for subsequent playbooks to use

## Notes

- **Project Context**: Must execute in web_page or website project context
- **Sandbox Path**: Ensure using Project Sandbox path, not artifacts path
- **Schema Validation**: Must use Pydantic schema to validate generated specification
- **Backward Compatibility**: If no project context, can downgrade to artifacts path (but will prompt user)
- **Format Consistency**: Ensure generated YAML format conforms to schema definition

## Related Documentation

- **Schema Definition**: `capabilities/web_generation/schema/site_spec_schema.py`
- **Schema Documentation**: `capabilities/web_generation/docs/site_spec_schema.md`
- **Complete Website Generation Workflow**: `capabilities/web_generation/docs/complete-pipeline-workflow.md`

