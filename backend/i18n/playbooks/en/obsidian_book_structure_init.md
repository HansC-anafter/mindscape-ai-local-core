---
playbook_code: obsidian_book_structure_init
version: 1.0.0
capability_code: obsidian_book
name: Initialize Obsidian Book Structure
description: Initialize book structure in Obsidian vault for a given year, creating necessary folders and template files
tags:
  - obsidian
  - book
  - structure
  - initialization

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
icon: 📚
---

# Initialize Obsidian Book Structure - SOP

## Goal

Initialize book structure in Obsidian vault for a given year, creating necessary folders and template files with frontmatter.

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for active book project
- Check if there is a `project_id` in execution context
- If yes, confirm project type is `book` or `obsidian_book`
- If no, prompt user to create a book project first

#### Step 0.2: Get Obsidian Vault Path
- Read Obsidian vault path from workspace settings:
  ```python
  workspace = await store.get_workspace(workspace_id)
  vault_paths = workspace.settings.get("obsidian", {}).get("vault_paths", [])
  ```
- If multiple vaults, ask user to select one
- If no vault path configured, prompt user to configure first

#### Step 0.3: Get Year and Book Information
- Get year from user input or project context
- If not provided, use current year
- Get book title and slug (if not provided, use defaults)

### Phase 1: Validate and Prepare

#### Step 1.1: Validate Vault Path
- Confirm vault path exists and is writable
- Check if `books/` directory exists, create if not

#### Step 1.2: Check if Book Structure Already Exists
- Check if `books/{year}/` directory already exists
- If exists, ask user if they want to overwrite or update
- If not exists, continue initialization

#### Step 1.3: Generate Book Identifier
- Generate book identifier: `{year}-{book-slug}`
- If slug not provided, use default (e.g., "mindscape")

### Phase 2: Create Directory Structure

#### Step 2.1: Create Book Root Directory
- Create `books/{year}/` directory
- Create `books/{year}/chapters/` directory
- Create `books/{year}/assets/` directory
- Create `books/{year}/assets/images/` directory
- Create `books/{year}/assets/attachments/` directory

#### Step 2.2: Verify Directory Creation
- Confirm all directories created successfully
- If creation fails, log error and prompt user

### Phase 3: Generate Template Files

#### Step 3.1: Generate `00-intro.md` (Book Introduction)

**File Path**: `books/{year}/00-intro.md`

**Frontmatter**:
```yaml
---
book: "{year}-{book-slug}"
type: "intro"
year: {year}
title: "{Book Title}"
description: "{Book Description}"
status: "draft"
tags: ["book", "{book-slug}"]
created_at: "{Current Date}"
updated_at: "{Current Date}"
---
```

**Content Template**:
```markdown
# {Book Title}

{Book Description}

## Table of Contents

(Chapter list will be added later)

## About This Book

(About the book description)
```

#### Step 3.2: Generate `01-chapter-structure.md` (Chapter Structure Planning)

**File Path**: `books/{year}/01-chapter-structure.md`

**Frontmatter**:
```yaml
---
book: "{year}-{book-slug}"
type: "structure"
year: {year}
status: "draft"
tags: ["book", "structure"]
created_at: "{Current Date}"
updated_at: "{Current Date}"
---
```

**Content Template**:
```markdown
# Chapter Structure Planning

## Chapter List

(Chapter structure will be planned later)

## Chapter Planning Notes

(Chapter planning description)
```

### Phase 4: Save Files

#### Step 4.1: Save Book Introduction File
- Use `filesystem_write_file` tool to save `00-intro.md`
- Ensure frontmatter format is correct
- Ensure content format is correct

#### Step 4.2: Save Chapter Structure File
- Use `filesystem_write_file` tool to save `01-chapter-structure.md`
- Ensure frontmatter format is correct
- Ensure content format is correct

#### Step 4.3: Verify File Creation
- Confirm all files created successfully
- Verify frontmatter format
- If creation fails, log error and prompt user

### Phase 5: Generate Summary and Next Steps

#### Step 5.1: Generate Initialization Summary
- List created directory structure
- List created files
- Provide book identifier and path information

#### Step 5.2: Provide Next Steps Suggestions
- Suggest next step: Use `yearly_personal_book` playbook to generate content
- Suggest next step: Manually create chapter structure
- Provide usage instructions for related playbooks

## Input Parameters

- `year` (optional): Year, defaults to current year
- `book_title` (optional): Book title
- `book_slug` (optional): Book slug, defaults to "mindscape"
- `book_description` (optional): Book description
- `vault_path` (optional): Obsidian vault path (if not configured in settings)

## Output

- Book root directory: `books/{year}/`
- Book introduction file: `books/{year}/00-intro.md`
- Chapter structure file: `books/{year}/01-chapter-structure.md`
- Directory structure: `chapters/`, `assets/`, etc.

## Expected Results

- ✅ Complete book directory structure created in Obsidian vault
- ✅ Template files with frontmatter generated
- ✅ All files conform to Obsidian Book Structure Convention
- ✅ User can start writing using the book structure

## Notes

- If book structure already exists, will ask user if they want to overwrite
- Need to ensure Obsidian vault path is correctly configured
- Frontmatter must conform to specification (refer to `frontmatter-schema.yaml`)
- File paths use forward slashes `/`, conforming to Obsidian's internal path format

## Related Documentation

- **Structure Convention**: `docs/obsidian-book-structure-convention.md`
- **Frontmatter Schema**: `docs/frontmatter-schema.yaml`

