---
playbook_code: personal_writeback
version: 1.0.0
capability_code: walkto_lab
name: Personal Writeback
description: |
  Write back personal preferences, state updates, and rules to your value system.
  Extract preferences → Update states → Generate rules.
tags:
  - walkto
  - universe
  - writeback
  - personalization

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - walkto_writeback_universe
  - cloud_capability.call

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🌌
---

# Personal Writeback - SOP

## Objective

Enable users to write back their personal preferences, states, and rules after a walk session or interaction, updating their personal value system with:

1. **Preference Extraction**: Extract price sensitivity, aesthetic preferences, material preferences
2. **State Updates**: Update state map (what state → what preference)
3. **Rule Generation**: Generate 3-7 personal choice rules
4. **Trust Evidence Collection**: Collect moments when user felt understood
5. **Taboo Updates**: Update what not to buy/like/avoid

**Core Value**:
- Build a personal value system that evolves with each interaction
- Transform experiences into actionable rules
- Create a personalized universe that guides future choices

**Personal Value System Components**:
- **State Map**: What state → what preference (e.g., 'quiet' → 'cozy cafe')
- **Preferences**: Price sensitivity, aesthetic, material preferences
- **Rules**: 3-7 personal choice rules
- **Trust Evidence**: Moments when user felt understood
- **Taboos**: What not to buy/like/avoid

## Execution Steps

### Phase 0: Preparation

**Execution Order**:
1. Step 0.0: Identify writeback context
2. Step 0.1: Get existing universe
3. Step 0.2: Collect session/interaction data

#### Step 0.0: Identify Writeback Context

Get writeback context:
- `session_id`: Session identifier (if writing back from session)
- `user_id`: User identifier
- `interaction_type`: Type of interaction (session/standalone/cohort)
- `writeback_trigger`: What triggered this writeback

**Output**:
- `writeback_context`: Writeback context object
- `user_id`: User identifier
- `session_id`: Session identifier (if applicable)

#### Step 0.1: Get Existing Value System

Get user's existing personal value system:
- Retrieve current universe from database
- Load state map, preferences, rules, taboos
- Understand current universe state

**Output**:
- `existing_universe`: Buyer Universe object
- `current_state_map`: Current state map
- `current_preferences`: Current preferences
- `current_rules`: Current rules list
- `current_taboos`: Current taboos list

#### Step 0.2: Collect Session/Interaction Data

Collect data from session or interaction:
- Session observations and artifacts
- User's reactions and feedback
- Moments of understanding or connection
- Preferences expressed during interaction

**Output**:
- `session_data`: Session/interaction data object
- `observations`: Observations from session
- `user_feedback`: User's feedback and reactions
- `interaction_artifacts`: Artifacts from interaction

### Phase 1: Preference Extraction

**Execution Order**:
1. Step 1.0: Extract price sensitivity
2. Step 1.1: Extract aesthetic preferences
3. Step 1.2: Extract material preferences
4. Step 1.3: Extract atmosphere preferences

#### Step 1.0: Extract Price Sensitivity

Extract price sensitivity from interaction:
- Analyze user's reactions to price points
- Identify price sensitivity level (low/medium/high)
- Extract specific price preferences

**Price Sensitivity Extraction**:
```
Price Sensitivity Analysis:

User Reactions:
- [Reaction 1] - Indicates [sensitivity level]
- [Reaction 2] - Indicates [sensitivity level]

Extracted Sensitivity: [Low/Medium/High]

Specific Preferences:
- [Preference 1]
- [Preference 2]
```

**Output**:
- `price_sensitivity`: Price sensitivity level
- `price_preferences`: Specific price preferences
- `price_evidence`: Evidence for price sensitivity

#### Step 1.1: Extract Aesthetic Preferences

Extract aesthetic preferences from interaction:
- Analyze user's reactions to aesthetics
- Identify preferred styles, colors, designs
- Extract aesthetic preferences

**Aesthetic Preference Extraction**:
```
Aesthetic Preference Analysis:

User Reactions:
- [Reaction 1] - Indicates [aesthetic preference]
- [Reaction 2] - Indicates [aesthetic preference]

Extracted Preferences:
- Style: [Preferred styles]
- Colors: [Preferred colors]
- Design: [Preferred design elements]
```

**Output**:
- `aesthetic_preferences`: Aesthetic preferences object
- `style_preferences`: Style preferences list
- `color_preferences`: Color preferences list

#### Step 1.2: Extract Material Preferences

Extract material preferences from interaction:
- Analyze user's reactions to materials
- Identify preferred materials, textures, qualities
- Extract material preferences

**Material Preference Extraction**:
```
Material Preference Analysis:

User Reactions:
- [Reaction 1] - Indicates [material preference]
- [Reaction 2] - Indicates [material preference]

Extracted Preferences:
- Materials: [Preferred materials]
- Textures: [Preferred textures]
- Qualities: [Preferred qualities]
```

**Output**:
- `material_preferences`: Material preferences object
- `preferred_materials`: Preferred materials list
- `texture_preferences`: Texture preferences list

#### Step 1.3: Extract Atmosphere Preferences

Extract atmosphere preferences from interaction:
- Analyze user's reactions to atmosphere
- Identify preferred atmospheres, moods, environments
- Extract atmosphere preferences

**Atmosphere Preference Extraction**:
```
Atmosphere Preference Analysis:

User Reactions:
- [Reaction 1] - Indicates [atmosphere preference]
- [Reaction 2] - Indicates [atmosphere preference]

Extracted Preferences:
- Atmospheres: [Preferred atmospheres]
- Moods: [Preferred moods]
- Environments: [Preferred environments]
```

**Output**:
- `atmosphere_preferences`: Atmosphere preferences object
- `preferred_atmospheres`: Preferred atmospheres list
- `mood_preferences`: Mood preferences list

### Phase 2: State Updates

**Execution Order**:
1. Step 2.0: Identify state transitions
2. Step 2.1: Map states to preferences
3. Step 2.2: Update state map
4. Step 2.3: Validate state map consistency

#### Step 2.0: Identify State Transitions

Identify state transitions from interaction:
- What states did user experience?
- What triggered state changes?
- What states led to what preferences?

**State Transition Analysis**:
```
State Transitions Identified:

States Experienced:
- [State 1]: [When/Why]
- [State 2]: [When/Why]
- [State 3]: [When/Why]

State Transitions:
- [State A] → [State B]: [Trigger]
- [State B] → [State C]: [Trigger]
```

**Output**:
- `states_experienced`: States experienced list
- `state_transitions`: State transitions list
- `state_triggers`: State triggers identified

#### Step 2.1: Map States to Preferences

Map states to preferences:
- What preference does each state lead to?
- Create state → preference mappings
- Identify patterns in state-preference relationships

**State-Preference Mapping**:
```
State-Preference Mappings:

[State 1] → [Preference 1]: [Context/Reason]
[State 2] → [Preference 2]: [Context/Reason]
[State 3] → [Preference 3]: [Context/Reason]

Patterns:
- [Pattern 1]
- [Pattern 2]
```

**Output**:
- `state_preference_mappings`: State-preference mappings list
- `mapping_patterns`: Patterns in mappings

#### Step 2.2: Update State Map

Update user's state map with new mappings:
- Merge new mappings with existing state map
- Resolve conflicts (if any)
- Update state map in universe

**State Map Update Format**:
```
State Map Updated:

New Mappings Added:
- [State] → [Preference]: [Context]

Updated State Map:
- [State 1] → [Preference 1]
- [State 2] → [Preference 2]
- [State 3] → [Preference 3]
...

Total States: [count]
```

**Output**:
- `updated_state_map`: Updated state map object
- `new_mappings`: New mappings added
- `conflicts_resolved`: Conflicts resolved (if any)

#### Step 2.3: Validate State Map Consistency

Validate state map consistency:
- Check for conflicting mappings
- Ensure mappings are logical
- Validate state map completeness

**Validation Checks**:
- ✅ No conflicting state → preference mappings
- ✅ Mappings are logically consistent
- ✅ State map is complete (at least 5 states)

**Output**:
- `state_map_valid`: Boolean
- `validation_issues`: Validation issues list (if any)

### Phase 3: Rule Generation

**Execution Order**:
1. Step 3.0: Extract rule patterns
2. Step 3.1: Generate candidate rules
3. Step 3.2: Refine and validate rules
4. Step 3.3: Finalize rules (3-7 rules)

#### Step 3.0: Extract Rule Patterns

Extract patterns that can become rules:
- Identify decision patterns from interaction
- Extract "when X, choose Y" patterns
- Identify consistent choice patterns

**Rule Pattern Extraction**:
```
Rule Patterns Extracted:

Pattern 1: [When X, choose Y]
- Evidence: [Evidence]
- Frequency: [Frequency]

Pattern 2: [When X, choose Y]
- Evidence: [Evidence]
- Frequency: [Frequency]

Pattern 3: [When X, choose Y]
- Evidence: [Evidence]
- Frequency: [Frequency]
```

**Output**:
- `rule_patterns`: Rule patterns list
- `pattern_evidence`: Evidence for each pattern
- `pattern_frequency`: Frequency of each pattern

#### Step 3.1: Generate Candidate Rules

Generate candidate rules from patterns:
- Convert patterns into actionable rules
- Ensure rules are specific and applicable
- Generate 5-10 candidate rules

**Candidate Rules Format**:
```
Candidate Rules Generated:

1. [Rule 1] - [Context/When to apply]
   Source: [Pattern/Evidence]

2. [Rule 2] - [Context/When to apply]
   Source: [Pattern/Evidence]

3. [Rule 3] - [Context/When to apply]
   Source: [Pattern/Evidence]
...
```

**Output**:
- `candidate_rules`: Candidate rules list (5-10 rules)
- `rule_sources`: Source for each rule

#### Step 3.2: Refine and Validate Rules

Refine and validate candidate rules:
- Remove duplicates or similar rules
- Ensure rules are specific and actionable
- Validate rules against existing universe
- Check for conflicts with existing rules

**Rule Refinement**:
```
Rules Refined:

Removed:
- [Rule X]: [Reason - duplicate/too vague/conflicts]

Kept:
- [Rule 1]: [Why it's good]
- [Rule 2]: [Why it's good]
- [Rule 3]: [Why it's good]
```

**Output**:
- `refined_rules`: Refined rules list
- `removed_rules`: Removed rules list with reasons
- `validation_results`: Validation results

#### Step 3.3: Finalize Rules (3-7 rules)

Finalize rules to 3-7 rules:
- Select most important and applicable rules
- Ensure rules cover different aspects
- Finalize rule list

**Final Rules Format**:
```
Final Rules (3-7 rules):

1. [Rule 1] - [Context/When to apply]
2. [Rule 2] - [Context/When to apply]
3. [Rule 3] - [Context/When to apply]
...

Rule Coverage:
- [Aspect 1]: Covered by [Rule X]
- [Aspect 2]: Covered by [Rule Y]
- [Aspect 3]: Covered by [Rule Z]
```

**Acceptance Criteria**:
- ✅ 3-7 rules generated
- ✅ Rules are specific and actionable
- ✅ Rules cover different aspects
- ✅ No conflicts with existing rules

**Output**:
- `final_rules`: Final rules list (3-7 rules)
- `rule_coverage`: Rule coverage analysis

### Phase 4: Trust Evidence and Taboos

**Execution Order**:
1. Step 4.0: Collect trust evidence
2. Step 4.1: Update taboos
3. Step 4.2: Finalize universe update

#### Step 4.0: Collect Trust Evidence

Collect moments when user felt understood:
- Identify moments of connection or understanding
- Extract trust-building moments
- Record trust evidence

**Trust Evidence Collection**:
```
Trust Evidence Collected:

Moment 1: [Description]
- When: [When]
- Why: [Why user felt understood]
- Impact: [Impact on trust]

Moment 2: [Description]
- When: [When]
- Why: [Why user felt understood]
- Impact: [Impact on trust]
```

**Output**:
- `trust_evidence`: Trust evidence list
- `trust_moments`: Trust moments identified

#### Step 4.1: Update Taboos

Update what user should not buy/like/avoid:
- Identify negative reactions or avoidances
- Extract taboos from interaction
- Update taboo list

**Taboo Update Format**:
```
Taboos Updated:

New Taboos Added:
- [Taboo 1]: [Reason/Context]
- [Taboo 2]: [Reason/Context]

Updated Taboo List:
- [Taboo 1]
- [Taboo 2]
- [Taboo 3]
...
```

**Output**:
- `updated_taboos`: Updated taboos list
- `new_taboos`: New taboos added

#### Step 4.2: Finalize Value System Update

Finalize value system update with all components:
- Combine all updates (preferences, states, rules, trust, taboos)
- Validate universe completeness
- Save updated universe

**Value System Update Summary**:
```
Universe Update Summary:

Preferences Updated:
- Price sensitivity: [Updated]
- Aesthetic: [Updated]
- Material: [Updated]
- Atmosphere: [Updated]

State Map Updated:
- New states: [Count]
- New mappings: [Count]

Rules Updated:
- New rules: [Count]
- Total rules: [Count] (3-7)

Trust Evidence:
- New moments: [Count]

Taboos Updated:
- New taboos: [Count]
```

**Output**:
- `universe_updated`: Boolean
- `update_summary`: Update summary object
- `updated_universe`: Updated Buyer Universe object

## Acceptance Criteria

### Preference Extraction
- ✅ Price sensitivity extracted
- ✅ Aesthetic preferences extracted
- ✅ Material preferences extracted
- ✅ Atmosphere preferences extracted

### State Updates
- ✅ State transitions identified
- ✅ States mapped to preferences
- ✅ State map updated
- ✅ State map validated (at least 5 states)

### Rule Generation
- ✅ 3-7 rules generated
- ✅ Rules are specific and actionable
- ✅ Rules cover different aspects
- ✅ No conflicts with existing rules

### Trust Evidence and Taboos
- ✅ Trust evidence collected
- ✅ Taboos updated
- ✅ Value system update finalized

## Error Handling

### Preparation Errors
- If universe not found: Create new universe for user
- If session data missing: Prompt user to provide data

### Preference Extraction Errors
- If preferences unclear: Prompt user for clarification
- If extraction fails: Use default preferences or retry

### State Update Errors
- If state transitions unclear: Prompt user for clarification
- If state map conflicts: Resolve conflicts or prompt user

### Rule Generation Errors
- If insufficient patterns: Use existing rules or prompt for more input
- If rules cannot be generated: Use default rules or retry
- If rule conflicts: Resolve conflicts or prompt user

### Finalization Errors
- If universe update fails: Retry and inform user
- If validation fails: Fix issues and retry

## Notes

- Personal writeback is critical for personalization
- Rules should be specific and actionable (3-7 rules)
- State map should have at least 5 states
- Trust evidence helps build long-term relationship
- Taboos help avoid negative experiences
- Personal value system evolves with each interaction

