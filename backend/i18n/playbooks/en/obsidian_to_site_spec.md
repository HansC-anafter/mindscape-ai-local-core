---
playbook_code: obsidian_to_site_spec
version: 1.0.0
capability_code: obsidian_book
name: Obsidian Book to Site Spec
description: Scan book structure in Obsidian vault, read frontmatter and content, generate site specification document (site_structure.yaml)
tags:
  - obsidian
  - book
  - website
  - site-spec
  - conversion

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - filesystem_read_file
  - filesystem_write_file

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: planner
icon: 🔄
---

# Obsidian Book to Site Spec - SOP

## Goal

Scan book structure in Obsidian vault, read frontmatter and content, generate `site_structure.yaml` site specification document to Project Sandbox.

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for active book or website project
- Check if there is a `project_id` in execution context
- If yes, confirm project type is `book`, `obsidian_book`, or `website`
- If no, prompt user to create a project first

#### Step 0.2: Get Project Sandbox Path
- If project context exists, use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- Ensure `spec/` directory exists

#### Step 0.3: Get Obsidian Vault Path
- Read Obsidian vault path from workspace settings
- If multiple vaults, ask user to select one
- If not configured, prompt user to configure first

#### Step 0.4: Get Year and Book Information
- Get year from user input or project context
- If not provided, try to derive from Obsidian structure (scan `books/` directory)

### Phase 1: Scan Obsidian Book Structure

#### Step 1.1: Read Book Root Directory
- Scan `books/{year}/` directory
- Read `00-intro.md` to get basic book information
- Parse frontmatter to get book title, description, etc.

#### Step 1.2: Scan Chapter Directories
- Scan `books/{year}/chapters/` directory
- For each chapter directory:
  - Read `00-intro.md` to get chapter information
  - Scan all section files (`01-*.md`, `02-*.md`, ...)
  - Parse frontmatter for each file

#### Step 1.3: Build Page Tree Structure
- Build hierarchical structure based on `chapter` and `section` fields in frontmatter
- Sort by `order` field
- Filter pages with `status` as "ready" (optional, based on requirements)

### Phase 2: Parse Frontmatter

#### Step 2.1: Parse Book-Level Frontmatter
- Read frontmatter from `00-intro.md`
- Extract: `book`, `year`, `title`, `description`, `tags`

#### Step 2.2: Parse Chapter Frontmatter
- For each chapter's `00-intro.md`:
  - Extract: `chapter`, `slug`, `title`, `description`, `status`, `order`

#### Step 2.3: Parse Section Frontmatter
- For each section file:
  - Extract: `chapter`, `section`, `slug`, `title`, `description`, `status`, `order`

### Phase 3: Generate Site Specification

#### Step 3.1: Build Site Basic Information
- Site title: Use book title
- Site description: Use book description
- Base URL: `/books/{year}`

#### Step 3.2: Build Page List
- Book introduction page:
  - route: `/`
  - title: Book title
  - source: `/books/{year}/00-intro.md`
  - type: `intro`
  - status: Read from frontmatter

- Chapter pages:
  - route: `/chapters/{chapter-slug}`
  - title: Chapter title
  - source: `/books/{year}/chapters/{chapter-slug}/00-intro.md`
  - type: `chapter`
  - sections: Section list

- Section pages:
  - route: `/chapters/{chapter-slug}/{section-slug}`
  - title: Section title
  - source: `/books/{year}/chapters/{chapter-slug}/{section-number}-{section-slug}.md`
  - type: `section`
  - status: Read from frontmatter

#### Step 3.3: Build Navigation Structure
- Top Navigation:
  - Home: `/`
  - Chapters: `/chapters`

- Sidebar Navigation:
  - Build tree navigation based on chapter structure
  - Include hierarchical relationship between chapters and sections

### Phase 4: Generate YAML File

#### Step 4.1: Build YAML Structure
- Use Python's `yaml` library to build YAML structure
- Ensure format conforms to specification

#### Step 4.2: Generate site_structure.yaml
- File path: `{sandbox_path}/spec/site_structure.yaml`
- Use `filesystem_write_file` tool to save

**YAML Format Example**:
```yaml
site:
  title: "{Book Title}"
  description: "{Book Description}"
  base_url: "/books/{year}"

pages:
  - route: "/"
    title: "Introduction"
    source: "/books/{year}/00-intro.md"
    type: "intro"
    status: "ready"

  - route: "/chapters/{chapter-slug}"
    title: "{Chapter Title}"
    source: "/books/{year}/chapters/{chapter-slug}/00-intro.md"
    type: "chapter"
    sections:
      - route: "/chapters/{chapter-slug}/{section-slug}"
        title: "{Section Title}"
        source: "/books/{year}/chapters/{chapter-slug}/{section-number}-{section-slug}.md"
        status: "ready"

navigation:
  top:
    - label: "Home"
      route: "/"
    - label: "Chapters"
      route: "/chapters"
  sidebar:
    - label: "{Chapter Title}"
      route: "/chapters/{chapter-slug}"
      children:
        - label: "{Section Title}"
          route: "/chapters/{chapter-slug}/{section-slug}"
```

### Phase 5: Validate and Summary

#### Step 5.1: Validate Generated YAML
- Check if YAML format is correct
- Check if all required fields exist
- Check if routes are unique

#### Step 5.2: Generate Conversion Summary
- List scanned book information
- List number of generated pages
- List navigation structure
- Provide file path

## Input Parameters

- `year` (required): Year
- `vault_path` (optional): Obsidian vault path (if not configured in settings)
- `book_slug` (optional): Book slug (if not provided, derive from Obsidian structure)
- `filter_status` (optional): Filter status (e.g., only include pages with "ready" status)

## Output

- Site specification file: `spec/site_structure.yaml`
- File location: `spec/` directory in Project Sandbox

## Expected Results

- ✅ Successfully scan book structure in Obsidian vault
- ✅ Successfully parse all frontmatter
- ✅ Successfully generate `site_structure.yaml` file
- ✅ File format is correct and meets website generation requirements

## Technical Points

### Frontmatter Parsing

Use `python-frontmatter` library to parse frontmatter:
```python
import frontmatter

with open(file_path, 'r', encoding='utf-8') as f:
    post = frontmatter.load(f)
    metadata = post.metadata
    content = post.content
```

### File Scanning

Recursively scan `books/{year}/` directory:
```python
from pathlib import Path

book_dir = Path(vault_path) / "books" / str(year)
for md_file in book_dir.rglob("*.md"):
    # Process file
```

### YAML Generation

Use `pyyaml` library to generate YAML:
```python
import yaml

site_structure = {
    "site": {...},
    "pages": [...],
    "navigation": {...}
}

yaml_content = yaml.dump(site_structure, allow_unicode=True, sort_keys=False)
```

## Notes

- Need to ensure Obsidian vault path is correctly configured
- Need to ensure book structure conforms to Obsidian Book Structure Convention
- Frontmatter must conform to specification
- Route slugs must be unique
- File paths use forward slashes `/`, conforming to Obsidian's internal path format

## Related Documentation

- **Structure Convention**: `docs/obsidian-book-structure-convention.md`
- **Frontmatter Schema**: `docs/frontmatter-schema.yaml`
- **Web Generation Path**: `../web_generation/docs/web-generation-path.md`

