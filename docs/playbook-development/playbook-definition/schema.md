# Playbook Definition Schema

Complete schema documentation for playbook JSON definitions.

## Basic Structure

```json
{
  "version": "1.0.0",
  "playbook_code": "your_playbook",
  "kind": "user_workflow",
  "metadata": { ... },
  "execution_profile": { ... },
  "steps": [ ... ],
  "inputs": { ... },
  "outputs": { ... }
}
```

## execution_profile (v3.1)

**Type**: `object` (optional)
**Description**: Declarative requirements for model routing. The system `CapabilityProfileResolver` reads this to determine which model/runtime to use — playbook authors should NOT hardcode concrete model names.

**Fields**:
- `reasoning` (string): Quality tier — `"fast"`, `"standard"`, `"precise"`. Default: `"standard"`
- `modalities` (array of strings): Required modalities — `["text"]`, `["text", "vision"]`
- `output_mode` (string): Expected output — `"json"`, `"markdown"`, `"structured"`
- `context_need` (string): Context window need — `"low"`, `"medium"`, `"high"`
- `locality` (string): Execution locality — `"local_preferred"`, `"cloud_ok"`, `"local_only"`

> [!IMPORTANT]
> Do NOT put concrete model names (e.g. `"gpt-4o"`) in `execution_profile`.
> Use declarative requirements only. Model mapping is managed in the Settings page under **Models & Quota → profile_model_map**.

**Example** (vision playbook):
```json
{
  "execution_profile": {
    "reasoning": "standard",
    "modalities": ["text", "vision"],
    "output_mode": "json",
    "context_need": "medium",
    "locality": "local_preferred"
  }
}
```

**Example** (text-only, high quality):
```json
{
  "execution_profile": {
    "reasoning": "precise",
    "modalities": ["text"],
    "output_mode": "markdown",
    "context_need": "high",
    "locality": "cloud_ok"
  }
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
- `capability_code` (string, optional): Capability pack code for UI grouping

**Example**:
```json
{
  "name": "My Playbook",
  "description": "A simple playbook",
  "tags": ["example"],
  "scope": "user",
  "entry_agent_type": "workspace",
  "capability_code": "instagram"
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

