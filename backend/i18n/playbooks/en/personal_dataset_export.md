---
playbook_code: personal_dataset_export
version: 1.0.0
capability_code: walkto_lab
name: Personal Dataset Export
description: |
  Export your personal walk dataset with state map, preferences, rules, and route templates.
  Collect data → Format → Export in JSON/Markdown/Notion format.
tags:
  - walkto
  - dataset
  - export
  - personal-data

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - walkto_generate_dataset
  - cloud_capability.call

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 📦
---

# Personal Dataset Export - SOP

## Objective

Enable users to export their personal walk dataset, containing:

1. **Data Collection**: Collect all personal data (state map, preferences, rules, route templates)
2. **Formatting**: Format data according to export format (JSON/Markdown/Notion)
3. **Export**: Export dataset in requested format
4. **Delivery**: Deliver dataset to user

**Core Value**:
- Take away your personal value system and rules
- Portable dataset that can be used independently
- Complete record of your learning journey

**Dataset Components** (minimum requirements):
- **State Map**: Complete state preferences map (at least 5 states)
- **Preferences**: Price sensitivity, aesthetic, material preferences
- **Rules**: 3-7 personal choice rules
- **Route Templates**: Practice or route templates (at least 1 if applicable)
- **Next Steps**: Guidance for next phase

## Execution Steps

### Phase 0: Preparation

**Execution Order**:
1. Step 0.0: Identify export context
2. Step 0.1: Check dataset completeness
3. Step 0.2: Select export format

#### Step 0.0: Identify Export Context

Get export context:
- `user_id`: User identifier
- `track_id`: Track identifier (if exporting from track)
- `export_type`: Type of export (full/incremental/custom)
- `export_trigger`: What triggered this export

**Output**:
- `export_context`: Export context object
- `user_id`: User identifier
- `track_id`: Track identifier (if applicable)

#### Step 0.1: Check Dataset Completeness

Check if dataset is complete:
- Verify state map has at least 5 states
- Verify rules list has 3-7 rules
- Verify preferences are complete
- Check if route templates exist (if applicable)

**Completeness Check**:
```
Dataset Completeness Check:

State Map: [Count] states (Required: ≥5) ✅/❌
Rules: [Count] rules (Required: 3-7) ✅/❌
Preferences: [Complete/Incomplete] ✅/❌
Route Templates: [Count] templates (If applicable: ≥1) ✅/❌

Overall: [Complete/Incomplete]
```

**Output**:
- `dataset_complete`: Boolean
- `completeness_check`: Completeness check results
- `missing_components`: Missing components list (if incomplete)

#### Step 0.2: Select Export Format

Ask user to select export format:
- **JSON**: Structured JSON format (machine-readable)
- **Markdown**: Human-readable Markdown format
- **Notion**: Notion database format

**Format Selection**:
```
Export Format Options:

1. JSON - Structured format, machine-readable
2. Markdown - Human-readable format, easy to view
3. Notion - Notion database format, ready to import

Which format would you like? [JSON/Markdown/Notion]
```

**Output**:
- `export_format`: Export format (json/markdown/notion)
- `format_selected`: Boolean

### Phase 1: Data Collection

**Execution Order**:
1. Step 1.0: Collect state map
2. Step 1.1: Collect preferences
3. Step 1.2: Collect rules
4. Step 1.3: Collect route templates
5. Step 1.4: Collect next steps

#### Step 1.0: Collect State Map

Collect user's state map:
- Retrieve from buyer universe
- Verify completeness (at least 5 states)
- Organize by state → preference mappings

**State Map Collection**:
```
State Map Collected:

Total States: [Count]

State Mappings:
- [State 1] → [Preference 1]
- [State 2] → [Preference 2]
- [State 3] → [Preference 3]
- [State 4] → [Preference 4]
- [State 5] → [Preference 5]
...
```

**Output**:
- `state_map`: State map object
- `state_count`: Total number of states
- `state_mappings`: State-preference mappings list

#### Step 1.1: Collect Preferences

Collect user's preferences:
- Price sensitivity
- Aesthetic preferences
- Material preferences
- Atmosphere preferences

**Preference Collection**:
```
Preferences Collected:

Price Sensitivity: [Low/Medium/High]
Aesthetic Preferences: [Preferences]
Material Preferences: [Preferences]
Atmosphere Preferences: [Preferences]
```

**Output**:
- `preferences`: Preferences object
- `preference_categories`: Preference categories list

#### Step 1.2: Collect Rules

Collect user's personal rules:
- Retrieve from buyer universe
- Verify count (3-7 rules)
- Organize rules by category or priority

**Rule Collection**:
```
Rules Collected:

Total Rules: [Count] (Required: 3-7)

Rules:
1. [Rule 1]
2. [Rule 2]
3. [Rule 3]
...
```

**Output**:
- `rules`: Rules list (3-7 rules)
- `rule_count`: Total number of rules
- `rules_validated`: Boolean

#### Step 1.3: Collect Route Templates

Collect route templates (if applicable):
- Retrieve from walk sessions or track
- Organize by type or purpose
- Include template details

**Route Template Collection**:
```
Route Templates Collected:

Total Templates: [Count] (If applicable: ≥1)

Templates:
1. [Template 1] - [Type/Purpose]
2. [Template 2] - [Type/Purpose]
...
```

**Output**:
- `route_templates`: Route templates list
- `template_count`: Total number of templates

#### Step 1.4: Collect Next Steps

Collect next steps guidance:
- Generate based on current progress
- Provide actionable next steps
- Include recommendations

**Next Steps Collection**:
```
Next Steps Collected:

Guidance for Next Phase:

1. [Next Step 1]
2. [Next Step 2]
3. [Next Step 3]
...
```

**Output**:
- `next_steps`: Next steps list
- `next_steps_generated`: Boolean

### Phase 2: Formatting

**Execution Order**:
1. Step 2.0: Format for JSON
2. Step 2.1: Format for Markdown
3. Step 2.2: Format for Notion

#### Step 2.0: Format for JSON

Format dataset as structured JSON:
- Create JSON structure
- Include all components
- Ensure valid JSON syntax

**JSON Format Structure**:
```json
{
  "user_id": "[user_id]",
  "track_id": "[track_id]",
  "version": "1.0.0",
  "created_at": "[timestamp]",
  "state_map": {
    "[state_1]": "[preference_1]",
    "[state_2]": "[preference_2]",
    ...
  },
  "preferences": {
    "price_sensitivity": "[level]",
    "aesthetic": {...},
    "material": {...},
    "atmosphere": {...}
  },
  "rules": [
    "[rule_1]",
    "[rule_2]",
    ...
  ],
  "route_templates": [
    {...},
    {...}
  ],
  "next_steps": [
    "[step_1]",
    "[step_2]",
    ...
  ]
}
```

**Output**:
- `json_dataset`: Formatted JSON dataset
- `json_valid`: Boolean (JSON validation)

#### Step 2.1: Format for Markdown

Format dataset as human-readable Markdown:
- Create Markdown structure
- Include sections and formatting
- Ensure readability

**Markdown Format Structure**:
```markdown
# Personal Walk Dataset

**User ID**: [user_id]
**Track ID**: [track_id]
**Version**: 1.0.0
**Created At**: [timestamp]

## State Map

[State] → [Preference]

- [State 1] → [Preference 1]
- [State 2] → [Preference 2]
...

## Preferences

### Price Sensitivity
[Level]

### Aesthetic Preferences
[Preferences]

### Material Preferences
[Preferences]

### Atmosphere Preferences
[Preferences]

## Personal Rules

1. [Rule 1]
2. [Rule 2]
3. [Rule 3]
...

## Route Templates

### Template 1
[Template details]

### Template 2
[Template details]
...

## Next Steps

1. [Next Step 1]
2. [Next Step 2]
...
```

**Output**:
- `markdown_dataset`: Formatted Markdown dataset
- `markdown_valid`: Boolean (Markdown validation)

#### Step 2.2: Format for Notion

Format dataset as Notion database format:
- Create Notion-compatible structure
- Include database schema
- Ensure import-ready format

**Notion Format Structure**:
```
Notion Database Format:

Database Schema:
- State Map (Title)
- Preferences (Text)
- Rules (Text)
- Route Templates (Text)
- Next Steps (Text)

Database Rows:
[Formatted for Notion import]
```

**Output**:
- `notion_dataset`: Formatted Notion dataset
- `notion_valid`: Boolean (Notion format validation)

### Phase 3: Export

**Execution Order**:
1. Step 3.0: Generate export file
2. Step 3.1: Validate export
3. Step 3.2: Save export

#### Step 3.0: Generate Export File

Generate export file based on selected format:
- Create file with formatted data
- Set appropriate file extension
- Include metadata

**File Generation**:
```
Export File Generated:

Format: [json/markdown/notion]
File Name: personal_dataset_[user_id]_[timestamp].[ext]
File Size: [size]
Location: [path/url]
```

**Output**:
- `export_file`: Export file path or URL
- `file_name`: File name
- `file_size`: File size

#### Step 3.1: Validate Export

Validate exported dataset:
- Check format correctness
- Verify data completeness
- Ensure all required components present

**Validation Checks**:
- ✅ Format is correct
- ✅ All required components present
- ✅ State map has ≥5 states
- ✅ Rules count is 3-7
- ✅ File is valid

**Output**:
- `export_valid`: Boolean
- `validation_results`: Validation results

#### Step 3.2: Save Export

Save export file:
- Save to storage
- Generate download link
- Record export metadata

**Export Saved**:
```
Export Saved:

File: [file_name]
Location: [storage_location]
Download Link: [download_url]
Export Date: [timestamp]
Format: [format]
```

**Output**:
- `export_saved`: Boolean
- `download_link`: Download link or URL
- `export_metadata`: Export metadata object

### Phase 4: Delivery

**Execution Order**:
1. Step 4.0: Present dataset summary
2. Step 4.1: Provide download
3. Step 4.2: Explain usage

#### Step 4.0: Present Dataset Summary

Present dataset summary to user:
- Show dataset components
- Highlight key information
- Display statistics

**Dataset Summary Format**:
```
Personal Dataset Summary

User: [user_id]
Track: [track_name] (if applicable)
Export Date: [date]

Components:
- State Map: [count] states
- Preferences: [categories] categories
- Rules: [count] rules
- Route Templates: [count] templates
- Next Steps: [count] steps

Format: [format]
File Size: [size]
```

**Output**:
- `summary_presented`: Boolean
- `dataset_summary`: Dataset summary object

#### Step 4.1: Provide Download

Provide download link or file:
- Share download link
- Or provide direct file download
- Include instructions

**Download Format**:
```
Download Your Dataset:

[Download Link] or [Download Button]

File: personal_dataset_[user_id]_[timestamp].[ext]
Format: [format]
Size: [size]

Valid for: [duration]
```

**Output**:
- `download_provided`: Boolean
- `download_link`: Download link
- `download_instructions`: Download instructions

#### Step 4.2: Explain Usage

Explain how to use the dataset:
- Explain format
- Provide usage examples
- Suggest next actions

**Usage Explanation**:
```
How to Use Your Dataset:

Format: [format]

Usage Examples:
- [Example 1]
- [Example 2]
- [Example 3]

Next Actions:
- [Action 1]
- [Action 2]
```

**Output**:
- `usage_explained`: Boolean
- `usage_guide`: Usage guide object

## Acceptance Criteria

### Data Collection
- ✅ State map collected (≥5 states)
- ✅ Preferences collected
- ✅ Rules collected (3-7 rules)
- ✅ Route templates collected (if applicable, ≥1)
- ✅ Next steps collected

### Formatting
- ✅ Dataset formatted correctly for selected format
- ✅ All components included
- ✅ Format validation passed

### Export
- ✅ Export file generated
- ✅ Export validated
- ✅ Export saved

### Delivery
- ✅ Dataset summary presented
- ✅ Download provided
- ✅ Usage explained

## Error Handling

### Preparation Errors
- If dataset incomplete: Prompt user to complete missing components
- If format not selected: Prompt user to select format

### Data Collection Errors
- If state map incomplete: Prompt user to complete state map
- If rules insufficient: Prompt user to generate more rules
- If data missing: Retry collection or inform user

### Formatting Errors
- If formatting fails: Retry formatting
- If format invalid: Fix format issues and retry

### Export Errors
- If export fails: Retry export
- If validation fails: Fix issues and retry
- If save fails: Retry save operation

### Delivery Errors
- If download link fails: Regenerate link
- If file not accessible: Check permissions and retry

## Notes

- Personal Dataset is the key deliverable and renewal reason
- Dataset must be complete (all required components)
- State map must have at least 5 states
- Rules must be 3-7 rules
- Route templates are optional but recommended if applicable
- Export formats: JSON (machine-readable), Markdown (human-readable), Notion (ready to import)
- Dataset is portable and can be used independently













