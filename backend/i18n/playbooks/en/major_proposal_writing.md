---
playbook_code: major_proposal_writing
version: 1.0.0
capability_code: content
name: Major Proposal Writing Assistant
description: Upload guidelines/templates, automatically extract template structure, and guide you through section-by-section proposal writing
tags:
  - writing
  - proposal
  - document
  - application

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
  - core_files.upload
  - core_files.extract_text
  - core_llm.generate
  - core_llm.structured_extract
  - core_export.markdown
  - core_export.docx
  - major_proposal.import_template_from_files
  - major_proposal.start_proposal_project
  - major_proposal.generate_section_draft
  - major_proposal.assemble_full_proposal

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: writer
icon: 📝
---

# Major Proposal Writing Assistant

## Goal

Assist you in writing major proposal documents (such as government grants, loan applications, startup proposals, etc.). By uploading guidelines or templates, the system automatically extracts template structure, then guides you through section-by-section content writing, and finally assembles a complete proposal document.

## Functionality

This Playbook will:

1. **Parse Template**: Upload guideline/template files, automatically extract text content and analyze template structure
2. **Create Project**: Confirm template structure and create new proposal project
3. **Write Sections**: Guide you through section-by-section content writing, AI generates section drafts based on your information
4. **Assemble Document**: Assemble all sections into complete proposal document and export as DOCX format

## Use Cases

- Government grant application documents
- Loan application documents
- Startup proposal documents
- Other major proposal documents

## Inputs

- `template_files`: Guideline/template files (PDF/DOCX, required)
- `template_type`: Template type (gov_grant, loan, startup, other)
- `project_name`: Project name (required)

## Outputs

- `template_id`: Created template ID
- `project_id`: Proposal project ID
- `proposal_markdown`: Complete proposal Markdown
- `proposal_docx_path`: Generated DOCX file path

## Steps (Conceptual)

1. Upload and parse template files
2. Create proposal project
3. Write sections (iterative)
4. Assemble complete document and export

### Phase 6: File Generation and Saving

#### Step 6.1: Save Proposal Draft
**Must** use `sandbox.write_file` tool to save proposal draft (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `proposal_draft.md` (relative path, relative to sandbox root)
- Content: Complete proposal draft (Markdown format)
- Format: Markdown format

#### Step 6.2: Save Proposal Outline
**Must** use `sandbox.write_file` tool to save proposal outline (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `proposal_outline.md` (relative path, relative to sandbox root)
- Content: Proposal structure and outline, including all sections and key points
- Format: Markdown format

#### Step 6.3: Save DOCX File (if generated)
If DOCX file has been generated, record the file path in the execution summary.

## Notes

- Template parsing: System automatically analyzes template structure, but may require manual confirmation and adjustment
- Content generation: AI-generated content requires manual review and adjustment
- Format requirements: Ensure final document meets application unit's format requirements
- Deadline: Note application deadline and reserve sufficient time to complete document
- All generated proposal documents are saved to files for future reference

