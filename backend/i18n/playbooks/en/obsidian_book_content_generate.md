---
playbook_code: obsidian_book_content_generate
version: 1.0.0
capability_code: obsidian_book
name: Generate Obsidian Book Content
description: Organize content from Mindscape conversations and notes, generate structured book files to Obsidian vault according to Obsidian Book Structure Convention
tags:
  - obsidian
  - book
  - content-generation
  - annual

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
icon: 📖
---

# Generate Obsidian Book Content - SOP

## Goal

Organize content from Mindscape conversations and notes from this year into structured book content according to Obsidian Book Structure Convention, output to Obsidian vault.

## Function Description

This Playbook will:

1. **Collect Data**: Retrieve all conversations and notes from this year from local Mindscape database
2. **Organize by Month**: Group data by month, generate a small chapter for each month
3. **Annual Summary**: Integrate 12 months of chapters into a complete annual yearbook
4. **Structured Output**: Output to Obsidian vault according to Obsidian Book Structure Convention, including complete frontmatter

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for active book project
- Check if there is a `project_id` in execution context
- If yes, confirm project type is `book` or `obsidian_book`
- If no, prompt user to create a book project first

#### Step 0.2: Get Obsidian Vault Path
- Read Obsidian vault path from workspace settings
- If multiple vaults, ask user to select one
- If not configured, prompt user to configure first

#### Step 0.3: Get Year and Book Information
- Get year from user input or project context
- If not provided, use current year
- Check if `books/{year}/` directory exists
  - If not exists, suggest user run `obsidian_book_structure_init` playbook first

### Phase 1: Collect Annual Data

#### Step 1.1: Query Mindscape Database
- Query all conversation records for specified year
- Query all notes for specified year
- Filter to only read content written to yourself (system only reads your conversations with Mindscape)

#### Step 1.2: Organize Data
- Sort by time order
- Group by month
- Identify themes and key content

### Phase 2: Generate Monthly Chapters

#### Step 2.1: Generate Chapter for Each Month
- For each month (1-12):
  - Analyze conversation and note content for that month
  - Identify main themes and key events
  - Generate chapter title and description
  - Generate chapter slug

#### Step 2.2: Create Chapter Directory Structure
- Create chapter directories under `books/{year}/chapters/`
- Naming format: `{month-number:02d}-{chapter-slug}`
- Example: `01-january-reflection`, `02-february-insights`

#### Step 2.3: Generate Chapter Files
- Create `00-intro.md` for each chapter (chapter introduction)
- Create content files for each chapter (split into multiple sections based on content)

**Chapter Introduction File (`chapters/{chapter-slug}/00-intro.md`)**:

**Frontmatter**:
```yaml
---
book: "{year}-{book-slug}"
chapter: {chapter_number}
section: 0
slug: "{chapter-slug}"
title: "{Chapter Title}"
description: "{Chapter Description}"
status: "draft"
order: {chapter_number}
tags: ["book", "{book-slug}", "month-{month}"]
created_at: "{Current Date}"
updated_at: "{Current Date}"
---
```

**Content**:
```markdown
# {Chapter Title}

{Chapter Description}

## This Month's Highlights

{Main content and highlights for this month}

## Sections

- [1. {Section Title}](01-{section-slug}.md)
- [2. {Section Title}](02-{section-slug}.md)
```

### Phase 3: Generate Section Content

#### Step 3.1: Analyze Content and Split into Sections
- Split each month's content into multiple sections based on themes and length
- Each section should have a clear theme
- Number of sections determined by content volume (typically 2-5 sections)

#### Step 3.2: Generate Section Files
- Create file for each section: `{section-number:02d}-{section-slug}.md`

**Section File Frontmatter**:
```yaml
---
book: "{year}-{book-slug}"
chapter: {chapter_number}
section: {section_number}
slug: "{section-slug}"
title: "{Section Title}"
description: "{Section Description}"
status: "draft"
order: {section_number}
tags: ["book", "{book-slug}", "{relevant-tags}"]
created_at: "{Current Date}"
updated_at: "{Current Date}"
---
```

**Content**:
- Relevant content extracted from Mindscape conversations and notes
- Polished and organized text
- Maintain original content context and thought process

### Phase 4: Update Book Introduction

#### Step 4.1: Update `00-intro.md`
- Read existing `books/{year}/00-intro.md`
- Update table of contents section, add links to all chapters
- Update book description (if needed)

#### Step 4.2: Update `01-chapter-structure.md`
- Read existing `books/{year}/01-chapter-structure.md`
- Update chapter list, include all generated chapters
- Add chapter planning notes

### Phase 5: Save Files

#### Step 5.1: Save All Chapter Files
- Use `filesystem_write_file` tool to save all chapter introduction files
- Use `filesystem_write_file` tool to save all section files
- Ensure frontmatter format is correct
- Ensure file paths conform to Obsidian Book Structure Convention

#### Step 5.2: Update Book-Level Files
- Update `00-intro.md` (add table of contents)
- Update `01-chapter-structure.md` (add chapter list)

#### Step 5.3: Verify File Creation
- Confirm all files created successfully
- Verify frontmatter format
- Verify file structure conforms to specification

### Phase 6: Generate Summary

#### Step 6.1: Generate Content Summary
- List number of generated chapters
- List number of generated sections
- Provide book path and structure information

#### Step 6.2: Provide Next Steps Suggestions
- Suggest user to view and edit content in Obsidian
- Suggest using `obsidian_to_site_spec` playbook to generate site specification
- Provide usage instructions for related playbooks

## Input Parameters

- `year` (optional): Year, defaults to current year
- `book_slug` (optional): Book slug, defaults to "mindscape"
- `vault_path` (optional): Obsidian vault path (if not configured in settings)
- `content_filter` (optional): Content filter conditions (e.g., only include conversations with specific tags)

## Output

- Book root directory: `books/{year}/`
- Chapter directories: `books/{year}/chapters/{chapter-slug}/`
- Chapter files: `00-intro.md` and section files for each chapter
- Updated book introduction: `00-intro.md` and `01-chapter-structure.md`

## Expected Results

- ✅ Complete annual book structure generated in Obsidian vault
- ✅ All files have frontmatter conforming to specification
- ✅ Content organized by month and theme
- ✅ User can view, edit, and further refine content in Obsidian

## Notes

- **Data Privacy**: All data only exists locally, will not be uploaded to cloud
- **Only Read Content Written to Yourself**: System only reads your conversations with Mindscape
- **Preview and Edit**: After generation, can preview and edit in Obsidian first, then decide whether to process further
- **No Auto-Publish**: Will not automatically publish or send to anyone
- **Need to Initialize Structure First**: Recommend running `obsidian_book_structure_init` playbook first to initialize book structure

## Differences from yearly_personal_book

**yearly_personal_book** (Local Core):
- Output to `artifacts/` directory
- Simple Markdown files
- No frontmatter
- No structured organization

**obsidian_book_content_generate** (Playbook Cloud):
- Output to Obsidian vault
- Conforms to Obsidian Book Structure Convention
- Complete frontmatter
- Structured chapter and section organization
- Can generate site specification later

## Related Documentation

- **Structure Convention**: `docs/obsidian-book-structure-convention.md`
- **Frontmatter Schema**: `docs/frontmatter-schema.yaml`
- **Initialization Playbook**: `obsidian_book_structure_init.md`

