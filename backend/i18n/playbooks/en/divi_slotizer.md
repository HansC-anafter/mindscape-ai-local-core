---
playbook_code: divi_slotizer
version: 1.0.0
capability_code: web_generation
name: Divi Template Slotizer
description: |
  Automate the slotization process for Divi Theme templates. Automatically scans variable fields from Divi Portability exported .json templates,
  inserts {{slot_id}} placeholders, and generates slots.schema.json and template.registry.json.
  Subsequent page generation only needs to fill slot values without touching layout, ensuring visual consistency.
tags:
  - web
  - divi
  - wordpress
  - template
  - automation
  - slotization

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
  - cloud_capability.call

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🎯
---

# Divi Template Slotizer - SOP

## Objective

Automate the processing of Divi Theme templates (exported as `.json` files via Portability) into slotized templates:

1. **Auto-scan variable fields**: Identify text, URL, image, and other variable content
2. **Insert slot placeholders**: Replace variable fields with `{{slot_id}}`
3. **Generate slot schema**: Create `slots.schema.json` defining all slot types, constraints, and default values
4. **Register template**: Generate `template.registry.json` recording template ID, hash, context, and version

**Core Value**:
- Eliminate manual placeholder insertion
- Ensure layout consistency (only fill values, don't touch design settings)
- Support mass automated page generation with visual consistency

## Execution Steps

### Phase 0: Check Project Context

**Execution Order**:
1. Step 0.0: Check for active web_page or website project
2. Step 0.1: Get Project Sandbox path
3. Step 0.2: Check input file (template_json)

#### Step 0.0: Check Project Context

- Check if `project_id` exists in execution context
- If yes, confirm project type is `web_page` or `website`
- If no, prompt user to create project first

#### Step 0.1: Get Project Sandbox Path

- Use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- Ensure `templates/divi/` directory exists (for storing processed templates)

#### Step 0.2: Check Input File

**Must** use `filesystem_read_file` tool to read Divi exported `.json` file:

- **File path**: Provided by user (may be uploaded file or existing file)
- **Full path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/templates/divi/input/{template_name}.json`

**Validate JSON format**:
- Ensure file is valid JSON
- Check if it contains Divi Portability standard structure
- If format is invalid, prompt user to re-export

**Output**:
- `template_json`: Parsed JSON object
- `template_file_path`: Original file path

### Phase 1: Fingerprint & Context Detection

#### Step 1.1: Calculate Template Hash

Calculate SHA256 hash of template for:
- Template version tracking
- Duplicate detection
- Integrity verification

**Output**:
- `template_hash`: SHA256 hash (full 64 characters)
- `template_hash_short`: First 8 characters (for template_id)

#### Step 1.2: Detect Context Type

Divi Portability exported files may come from three contexts:

1. **divi_library**: Divi Library items (Layouts, Modules, Sections)
2. **page_layout**: Complete page layout
3. **theme_builder**: Theme Builder templates (Header, Footer, Body)

**Auto-detection logic**: Check key fields in JSON structure

**Important**: Divi import has "context restrictions". Importing to wrong location will cause *This file should not be imported in this context* error, so context must be correctly identified.

**Output**:
- `context`: `divi_library` / `page_layout` / `theme_builder`
- `context_confidence`: Detection confidence (high/medium/low)

#### Step 1.3: Generate Template ID

Generate unique template_id, format: `{slug(name)}-{short_hash}`

**Output**:
- `template_id`: Unique template identifier
- `template_name`: Template name extracted from JSON (if exists)

### Phase 2: Candidate Slots Scanning

#### Step 2.1: Define Slot Policy

**Slot Policy Rules** (hardcoded, immutable):

**Allowed Module Types**:
- Text, Heading, Button, Image, Blurb, Testimonial, Pricing Table, CTA, Post Title, Post Content, Post Meta

**Allowed Fields**:
- `title`, `content`, `button_text`, `button_url`, `image_url`, `alt`, `subtitle`, `description`, `author`, `date`

**Fixed Non-Slot Fields** (layout consistency root):
- All spacing fields (padding, margin, gap)
- All color fields (background_color, text_color, border_color)
- All font fields (font_family, font_size, font_weight, line_height)
- All animation fields (animation_style, animation_duration)
- All breakpoint fields (responsive settings)
- All custom CSS fields

#### Step 2.2: Traverse JSON Tree to Scan Candidate Fields

Recursively traverse Divi JSON structure to find all eligible candidate fields.

**Output**:
- `candidate_slots`: List of candidate slots (typically 30-80)

### Phase 3: Slot Selection (Rule Priority + LLM Assistance)

#### Step 3.1: Hard Rule Must-Select Slots

**Hard Rule Must-Select** (almost always need to be slotted):
- Hero title / subtitle
- CTA button_text / button_url
- Hero image (or hero background image)

**Hard Rule Must-Exclude**:
- Footer copyright, fixed navigation text, brand declarations
- Any fields related to spacing / color / font

#### Step 3.2: LLM-Assisted Classification (Semantic Judgment)

For undecided candidates, use LLM for "semantic judgment" (not visual decisions).

**Output**:
- `llm_classified_slots`: LLM classification results (contains should_slot, slot_type, max_length, reason)

#### Step 3.3: Merge Selected Slots

Merge hard-rule selected and LLM-classified `should_slot=true` candidates.

**Validate selected count**:
- Ensure selected slot count is in reasonable range (e.g., 8-30)
- If too few (< 5), warn user may have missed important fields
- If too many (> 40), warn user may have selected fields that shouldn't be slotted

**Output**:
- `selected_slots`: Final selected slots list (10-20)

### Phase 4: Slot ID Naming (Reproducible, Trackable)

#### Step 4.1: Generate Slot ID (Machine Stable Key)

Use "JSON path + module_id + field_name" hash to ensure reproducibility.

**Output**:
- `slot_id`: Machine stable key (e.g., `s_7f2a9c_title`)

#### Step 4.2: Generate Slot Alias (Human Readable)

Use LLM or rules to assign an alias.

**Output**:
- `slot_alias`: Human-readable alias (e.g., `hero_title`)

### Phase 5: Patch Template (Insert Slot Placeholders)

#### Step 5.1: Replace Field Values with `{{slot_id}}`

For each selected slot, find corresponding field in original JSON and replace with `{{slot_id}}`.

**Output**:
- `template_patched_json`: Template JSON with `{{slot_id}}` inserted

#### Step 5.2: Save Patched Template

**Must** use `filesystem_write_file` tool to save processed template:

- **File path**: `templates/divi/patched/{template_id}.json`
- **Full path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/templates/divi/patched/{template_id}.json`

### Phase 6: Generate Slots Schema

#### Step 6.1: Build Slots Schema Structure

Generate `slots.schema.json` defining all slot types, constraints, and default values.

**Output**:
- `slots_schema`: Slots Schema JSON object

#### Step 6.2: Save Slots Schema

**Must** use `filesystem_write_file` tool to save:

- **File path**: `templates/divi/schemas/{template_id}.slots.schema.json`
- **Full path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/templates/divi/schemas/{template_id}.slots.schema.json`

### Phase 7: Register Template (Template Registry)

#### Step 7.1: Build Template Registry Entry

Generate `template.registry.json` or update registry.

**Output**:
- `registry_entry`: Template Registry Entry JSON object

#### Step 7.2: Save or Update Registry

**Option 1: Single File Registry** (recommended for PoC):
- **File path**: `templates/divi/registry.json`
- Read existing registry (if exists)
- Add or update entry
- Save back to file

**Option 2: Distributed Registry** (one entry file per template):
- **File path**: `templates/divi/registry/{template_id}.registry.json`
- Save entry file directly

**Must** use `filesystem_write_file` tool to save.

### Phase 8: Validator (Validation)

#### Step 8.1: JSON Syntax Validation

- Check if `template_patched_json` is valid JSON
- Check if `slots_schema` is valid JSON
- Check if `registry_entry` is valid JSON

#### Step 8.2: Slot Count Validation

- Check if `slot_count` is in reasonable range (8-30)
- If < 5, warn "may have missed important fields"
- If > 40, warn "may have selected fields that shouldn't be slotted"

#### Step 8.3: Slot Type Format Validation

- Check all `url` slot values conform to URL/path format
- Check all `image` slot values conform to URL or attachment id format
- Check all `text` slot values are within `max_length` limit

#### Step 8.4: Placeholder Position Validation

- Check if `{{slot_id}}` appears in "design setting fields" (should not appear)
- If found, mark as error and exclude that slot

#### Step 8.5: Context Validation (Optional but Strongly Recommended)

**Import to Staging Site for Real Test**:

1. Import `template_patched.json` to staging WordPress site
2. Check if *This file should not be imported in this context* error appears
3. If error appears, directly fail (indicates registry context detection is wrong)

**Note**: This step requires WordPress environment. If no staging site, can skip but will be marked as "unverified".

**Output**:
- `validation_results`: Validation results dictionary
- `validation_passed`: true/false
- `validation_warnings`: Warning list
- `validation_errors`: Error list

### Phase 9: Register Artifacts

#### Step 9.1: Register Output Artifacts

**Must** use `artifact_registry.register_artifact` to register output artifacts:

1. **Patched Template**:
   - **artifact_id**: `divi_template_patched_{template_id}`
   - **artifact_type**: `divi_template`
   - **path**: `templates/divi/patched/{template_id}.json`

2. **Slots Schema**:
   - **artifact_id**: `divi_slots_schema_{template_id}`
   - **artifact_type**: `json_schema`
   - **path**: `templates/divi/schemas/{template_id}.slots.schema.json`

3. **Template Registry Entry**:
   - **artifact_id**: `divi_template_registry_{template_id}`
   - **artifact_type**: `registry_entry`
   - **path**: `templates/divi/registry/{template_id}.registry.json` or `templates/divi/registry.json`

### Phase 10: Execution Record Saving

#### Step 10.1: Save Conversation History

**Must** use `filesystem_write_file` tool to save complete conversation history:

- File path: `artifacts/divi_slotizer/{{execution_id}}/conversation_history.json`
- Content: Complete conversation history (all user and assistant messages)
- Format: JSON format with timestamps and role information

#### Step 10.2: Save Execution Summary

**Must** use `filesystem_write_file` tool to save execution summary:

- File path: `artifacts/divi_slotizer/{{execution_id}}/execution_summary.md`
- Content:
  - Execution time
  - Execution ID
  - Playbook name
  - Input template file path
  - Template ID
  - Template Hash
  - Context
  - Slot count
  - Generated file list
  - Validation results
  - Warnings and errors (if any)

## Runtime Usage Flow (Subsequent Workflow)

Subsequent web-generation workflow using Slotizer output templates:

### 1. LLM Select Template

Select `template_id` from Template Registry.

### 2. LLM Generate Slot Values

Generate slot values according to `slots.schema.json`.

### 3. Generate Page JSON

Copy `template_patched.json`, replace all `{{slot_id}}` with actual content.

### 4. Import to WordPress

Import generated `page_json` to WordPress (via Divi Portability):
- Ensure import to correct context (according to registry context)
- Check if import succeeded
- If failed, record error and report

## Success Criteria

- ✅ Template Hash calculated
- ✅ Context correctly identified
- ✅ Template ID generated
- ✅ Candidate Slots scanned (30-80)
- ✅ Final Selected Slots (10-20)
- ✅ Slot ID and Alias generated
- ✅ Template Patched (inserted `{{slot_id}}`)
- ✅ Slots Schema generated
- ✅ Template Registry Entry created
- ✅ All validations passed
- ✅ Artifacts registered
- ✅ Execution records saved

## Notes

- **Project Context**: Must execute in web_page or website project context
- **Input File Format**: Must be valid JSON exported from Divi Portability
- **Context Detection**: Must correctly identify context, otherwise import will fail
- **Slot Count**: Recommended between 8-30. Too few may miss important fields, too many may select fields that shouldn't be slotted
- **Reproducibility**: Slot ID uses hash generation, ensuring template revisions can still map to same slots
- **Staging Validation**: Strongly recommend validating context detection on staging site

## Related Documentation

- **Template Registry Reference**: `docs/divi/divi_template_registry_reference.md`
- **Slotizer Implementation Guide**: `docs/divi/divi_slotizer_implementation_guide.md`
- **Slot Schema Examples**: `docs/divi/divi_slot_schema_examples.md`
- **Divi Portability Documentation**: https://www.elegantthemes.com/documentation/divi/library-import/
- **Context Error Fix Guide**: https://help.elegantthemes.com/en/articles/2612617-how-to-fix-the-this-file-should-not-be-imported-in-this-context-error-when-importing-a-json-file

