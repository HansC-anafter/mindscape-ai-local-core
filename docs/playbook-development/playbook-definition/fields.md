# Field Descriptions

Detailed descriptions of playbook definition fields.

## Top-Level Fields

### version

Playbook version following semantic versioning (MAJOR.MINOR.PATCH).

**Example**: `"1.0.0"`, `"2.1.3"`

### playbook_code

Unique identifier for the playbook. Must be snake_case and match the package name pattern.

**Pattern**: `[a-z][a-z0-9_]*`

**Example**: `"yearly_personal_book"`, `"course_writing"`

### kind

Type of playbook workflow.

**Values**:
- `"user_workflow"` - User-initiated workflow
- `"system_workflow"` - System-initiated workflow

## Metadata Fields

### name

Display name shown to users.

**Example**: `"Create Your Annual Book"`

### description

Brief description of what the playbook does.

**Example**: `"Organize monthly chapters from this year's Mindscape conversations"`

### tags

Array of tags for categorization and filtering.

**Example**: `["writing", "book", "yearly"]`

### scope

Playbook scope.

**Values**:
- `"system"` - System playbook (built-in)
- `"user"` - User playbook (custom)

### entry_agent_type

Agent type that can initiate this playbook.

**Values**: `"workspace"`, `"intent"`, etc.

### capability_code

Capability pack code this playbook belongs to. Used for grouping playbooks in the UI.

**Type**: `string` (optional)

**Description**: When set, playbooks with the same `capability_code` will be grouped together in a separate tab in the Playbooks page. If not set, the playbook will be grouped under "System Playbooks".

**Example**: `"instagram"`, `"web_generation"`, `"seo"`

**Note**: This field can be set in both:
- Markdown frontmatter (`.md` files): `capability_code: instagram`
- JSON metadata (`.json` files): `"capability_code": "instagram"`

## Step Fields

### id

Unique identifier for the step within the playbook.

**Example**: `"collect_data"`, `"process_results"`

### type

Step type.

**Values**:
- `"llm_call"` - LLM-based processing
- `"tool_call"` - Tool execution
- `"condition"` - Conditional logic

### tool

Tool identifier for tool-based steps.

**Format**: `{provider}.{tool_name}`

**Example**: `"core_llm.structured_extract"`, `"wordpress.create_post"`

### depends_on

Array of step IDs that must complete before this step runs.

**Example**: `["step1", "step2"]`

## Template Syntax

### Input References

- `{{input.field_name}}` - Reference playbook input
- `{{step.step_id.output_name}}` - Reference step output

### Example

```json
{
  "text": "User request: {{input.user_request}}\n\nPrevious result: {{step.collect_data.result}}"
}
```

---

**Status**: Content completed with field descriptions

