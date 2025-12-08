# Playbook Definition Schema

Complete schema documentation for playbook JSON definitions.

## Basic Structure

```json
{
  "version": "1.0.0",
  "playbook_code": "your_playbook",
  "kind": "user_workflow",
  "metadata": { ... },
  "steps": [ ... ],
  "inputs": { ... },
  "outputs": { ... }
}
```

## Required Fields

### version

**Type**: `string`
**Description**: Playbook version (semantic versioning)

**Example**: `"1.0.0"`

### playbook_code

**Type**: `string`
**Description**: Unique identifier for the playbook (snake_case)

**Example**: `"yearly_personal_book"`

### kind

**Type**: `string`
**Description**: Playbook kind

**Values**: `"user_workflow"`, `"system_workflow"`

### metadata

**Type**: `object`
**Description**: Playbook metadata

**Fields**:
- `name` (string): Display name
- `description` (string): Description
- `tags` (array of strings): Tags for categorization
- `scope` (string): `"system"` or `"user"`
- `entry_agent_type` (string): Entry point agent type

**Example**:
```json
{
  "name": "My Playbook",
  "description": "A simple playbook",
  "tags": ["example"],
  "scope": "user",
  "entry_agent_type": "workspace"
}
```

## Steps

**Type**: `array`
**Description**: Workflow steps

### Step Structure

```json
{
  "id": "step1",
  "type": "llm_call",
  "tool": "core_llm.structured_extract",
  "inputs": { ... },
  "outputs": { ... },
  "depends_on": ["step0"]
}
```

### Step Types

- `llm_call` - LLM-based step
- `tool_call` - Tool execution step
- `condition` - Conditional step

### Inputs

Step inputs use template syntax:
- `{{input.field_name}}` - Reference input
- `{{step.step_id.output_name}}` - Reference previous step output

**Example**:
```json
{
  "text": "Process: {{input.user_request}}\n\nData: {{step.collect_data.result}}"
}
```

### Outputs

Map step outputs to variables:

```json
{
  "result": "extracted_data.result",
  "summary": "extracted_data.summary"
}
```

## Inputs

**Type**: `object`
**Description**: Playbook input definitions

**Example**:
```json
{
  "user_request": {
    "type": "string",
    "description": "User's request",
    "required": true
  },
  "year": {
    "type": "string",
    "description": "Year to process",
    "default": "2025"
  }
}
```

## Outputs

**Type**: `object`
**Description**: Playbook output definitions

**Example**:
```json
{
  "result": {
    "description": "Processing result",
    "source": "step.final_step.result"
  }
}
```

## Complete Example

See [Yearly Book Example](../examples/yearly-book.md) for a complete playbook definition.

---

**Status**: Content completed with schema documentation

