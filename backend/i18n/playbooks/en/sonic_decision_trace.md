---
playbook_code: sonic_decision_trace
version: 1.0.0
locale: en
name: "A/B Listening Experiment & Path Recording"
description: "Record decision paths (like Git log)"
kind: user_workflow
capability_code: sonic_space
---

# A/B Listening Experiment & Path Recording

Record decision paths (like Git log)

## Overview

The A/B Listening Experiment & Path Recording playbook records decision paths during sound selection and navigation, similar to Git log. It tracks user choices, A/B comparisons, and decision history to enable backtracking and learning from past decisions.

**Key Features:**
- Record A/B listening decisions
- Create decision trace paths (like Git log)
- Track navigation history
- Enable backtracking to previous decisions
- Learn from decision patterns

**Purpose:**
This playbook enables users to track their sound selection journey and learn from past decisions. It's essential for iterative sound design workflows where users need to explore multiple options and revisit previous choices.

**Related Playbooks:**
- `sonic_navigation` - Record navigation decisions
- `sonic_intent_card` - Track intent card iterations
- `sonic_bookmark` - Link bookmarks to decision traces

For detailed specification, please refer to the spec file: `playbooks/specs/sonic_decision_trace.json`

## Inputs


## Outputs

See spec file for detailed output schema.

## Steps

### Step 1: Record Decision

Record A/B listening decision

- **Action**: `record_decision`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Create Trace

Create decision trace path (like Git log)

- **Action**: `create_trace`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## Guardrails

No guardrails defined.

## Required Capabilities

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## Data Locality

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## Use Cases

1. **A/B Comparison Tracking**
   - Record choices between sound options
   - Track which sounds were selected and why
   - Build decision history for analysis

2. **Iterative Design Workflow**
   - Track multiple iterations of sound selection
   - Enable backtracking to previous choices
   - Learn from decision patterns

3. **Decision Analysis**
   - Analyze decision patterns over time
   - Identify preferred sound characteristics
   - Improve future sound selection

## Examples

### Example 1: Record A/B Decision

```json
{
  "intent_card_id": "intent_123",
  "option_a_id": "segment_001",
  "option_b_id": "segment_002",
  "selected_option": "segment_001",
  "decision_reason": "More spacious feel"
}
```

**Expected Output:**
- `decision_trace` artifact with:
  - Decision record (timestamp, options, selection)
  - Link to intent card
  - Decision reason

## Technical Details

**Decision Recording:**
- Records A/B comparison choices
- Links decisions to intent cards
- Stores decision reasons and context
- Creates traceable decision paths

**Trace Structure:**
- Similar to Git log structure
- Linear or branching decision paths
- Timestamp and context for each decision
- Links to related artifacts (intent cards, segments)

**Tool Dependencies:**
- Decision tracking system

## Related Playbooks

- **sonic_navigation** - Record navigation decisions
- **sonic_intent_card** - Track intent card iterations
- **sonic_bookmark** - Link bookmarks to decision traces

## Reference

- **Spec File**: `playbooks/specs/sonic_decision_trace.json`
