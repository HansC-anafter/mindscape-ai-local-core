---
playbook_code: walk_session
version: 1.0.0
capability_code: walkto_lab
name: Walk Session
description: |
  Participate in a single walk session with exploration, convergence, and writeback.
  Follow the rhythm: Agreement → Exploration → Convergence → Writeback.
tags:
  - walkto
  - walk-session
  - co-learning
  - exploration

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - walkto_record_walk_session
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
icon: 🚶
---

# Walk Session - SOP

## Objective

Enable users to participate in a single walk session, following the rhythm:

1. **Agreement Phase**: Set expectations, confirm topic, understand lens perspective
2. **Exploration Phase**: Observe, ask questions, interact with environment and participants
3. **Convergence Phase**: Summarize findings, extract insights, identify patterns
4. **Writeback Phase**: Provide preferences, state updates, and generate personal rules

**Core Value**:
- Transform a single walk into a structured learning experience
- Extract actionable insights from field observations
- Build personal rules based on real experiences

**Session Structure** (60-90 minutes):
- **Agreement** (10-15 min): Set expectations and confirm understanding
- **Exploration** (30-45 min): Guided observation and interaction
- **Convergence** (20-30 min): Summarize and extract insights
- **Writeback** (10-15 min): Provide feedback and generate rules

## Execution Steps

### Phase 0: Preparation

**Execution Order**:
1. Step 0.0: Identify session context
2. Step 0.1: Get Lens Card and topic
3. Step 0.2: Confirm participation readiness

#### Step 0.0: Identify Session Context

Get session information:
- `session_id`: Session identifier (if joining existing session)
- `lens_id`: Associated Lens identifier
- `track_id`: Associated Track identifier (if part of Annual Track)
- `cohort_id`: Associated Cohort identifier (if part of cohort)

**Output**:
- `session_id`: Session identifier
- `lens_id`: Lens identifier
- `session_context`: Session context (standalone/cohort/track)

#### Step 0.1: Get Lens Card and Topic

Get Lens Card and session topic:
- Retrieve Lens Card from lens_id
- Get session topic and objectives
- Understand lens perspective and judgment criteria

**Output**:
- `lens_card`: Lens Card object
- `topic`: Session topic
- `judgment_criteria`: Judgment criteria list
- `perspective_model`: Perspective model

#### Step 0.2: Confirm Participation Readiness

Confirm user is ready to participate:
- Check if user has necessary materials (if required)
- Confirm user understands session structure
- Set user's initial state and expectations

**Output**:
- `user_ready`: Boolean
- `initial_state`: User's initial state
- `user_expectations`: User's expectations for session

### Phase 1: Agreement

**Execution Order**:
1. Step 1.0: Understand session objectives
2. Step 1.1: Confirm lens perspective
3. Step 1.2: Set personal expectations
4. Step 1.3: Agree on session structure

#### Step 1.0: Understand Session Objectives

Present session objectives to user:
- What will we explore today?
- What is the lens perspective we'll use?
- What are the expected outcomes?

**Objectives Format**:
```
Session Objectives:
- Topic: [Topic]
- Lens Perspective: [Lens perspective]
- Expected Outcomes:
  1. [Outcome 1]
  2. [Outcome 2]
  3. [Outcome 3]
```

**Output**:
- `session_objectives`: Session objectives object
- `user_understands`: Boolean (user confirms understanding)

#### Step 1.1: Confirm Lens Perspective

Present lens perspective to user:
- Show judgment criteria
- Explain perspective model
- Clarify what the lens helps us see

**Lens Perspective Format**:
```
Lens Perspective: [Lens Name]

What This Lens Helps Us See:
- [Perspective 1]
- [Perspective 2]
- [Perspective 3]

Judgment Criteria:
1. [Criterion 1]
2. [Criterion 2]
...
```

**Output**:
- `lens_perspective_confirmed`: Boolean
- `user_questions`: User's questions about lens (if any)

#### Step 1.2: Set Personal Expectations

Ask user about their expectations:
- What do you want to explore today?
- What kind of experience are you looking for? (quiet/social/exploration/relaxation)
- What are your personal goals for this session?

**Output**:
- `user_expectations`: User's expectations object
- `desired_experience_type`: Desired experience type
- `personal_goals`: Personal goals list

#### Step 1.3: Agree on Session Structure

Confirm session structure with user:
- Explain Agreement → Exploration → Convergence → Writeback rhythm
- Set time expectations for each phase
- Confirm user agrees to participate

**Session Structure Format**:
```
Session Structure:
1. Agreement (10-15 min): Set expectations and confirm understanding
2. Exploration (30-45 min): Observe, ask questions, interact
3. Convergence (20-30 min): Summarize findings and extract insights
4. Writeback (10-15 min): Provide feedback and generate rules

Total Duration: 60-90 minutes
```

**Output**:
- `session_structure_confirmed`: Boolean
- `user_agrees`: Boolean

### Phase 2: Exploration

**Execution Order**:
1. Step 2.0: Begin exploration
2. Step 2.1: Guide observation
3. Step 2.2: Facilitate interaction
4. Step 2.3: Collect observations

#### Step 2.0: Begin Exploration

Start exploration phase:
- Guide user to begin observing
- Provide observation prompts based on lens
- Encourage active engagement

**Exploration Prompts**:
- "What do you notice about [aspect]?"
- "How does this relate to the lens perspective?"
- "What questions does this raise for you?"
- "What feels important to you here?"

**Output**:
- `exploration_started`: Boolean
- `initial_observations`: Initial observations list

#### Step 2.1: Guide Observation

Guide user through structured observation:
- Focus on specific aspects based on lens
- Use judgment criteria as observation guide
- Encourage detailed, specific observations

**Observation Guidance**:
```
Observation Focus Areas:
1. [Focus area 1] - Based on lens perspective
2. [Focus area 2] - Based on lens perspective
3. [Focus area 3] - Based on lens perspective

Observation Prompts:
- What do you see/hear/feel?
- How does this match or differ from the lens perspective?
- What stands out to you?
```

**Output**:
- `observations`: Observations list
- `observation_details`: Detailed observation notes

#### Step 2.2: Facilitate Interaction

Facilitate interaction with environment and participants:
- Encourage questions and discussions
- Guide interactions based on lens perspective
- Collect interaction artifacts (photos, notes, etc.)

**Interaction Guidance**:
- Ask questions based on lens perspective
- Share observations with others (if in group)
- Engage with environment actively
- Document interesting moments

**Output**:
- `interactions`: Interactions list
- `interaction_artifacts`: Artifacts collected (photos, notes, etc.)
- `questions_asked`: Questions asked list

#### Step 2.3: Collect Observations

Collect all observations from exploration:
- Organize observations by theme
- Link observations to lens perspective
- Identify patterns or interesting points

**Observation Collection Format**:
```
Observations Collected:
1. [Observation 1] - Related to [lens aspect]
2. [Observation 2] - Related to [lens aspect]
3. [Observation 3] - Related to [lens aspect]
...

Patterns Identified:
- [Pattern 1]
- [Pattern 2]
...
```

**Output**:
- `all_observations`: Complete observations list
- `patterns_identified`: Patterns identified list
- `artifacts_collected`: All artifacts collected

### Phase 3: Convergence

**Execution Order**:
1. Step 3.0: Summarize findings
2. Step 3.1: Extract insights
3. Step 3.2: Identify key learnings
4. Step 3.3: Prepare for writeback

#### Step 3.0: Summarize Findings

Summarize what was discovered during exploration:
- Organize observations into themes
- Highlight key findings
- Connect findings to lens perspective

**Summary Format**:
```
Session Summary:

Key Findings:
1. [Finding 1] - [Brief description]
2. [Finding 2] - [Brief description]
3. [Finding 3] - [Brief description]

Themes:
- [Theme 1]: [Related findings]
- [Theme 2]: [Related findings]
...
```

**Output**:
- `session_summary`: Session summary object
- `key_findings`: Key findings list
- `themes`: Themes identified

#### Step 3.1: Extract Insights

Extract actionable insights from findings:
- What did we learn?
- What patterns emerged?
- What questions were answered or raised?

**Insights Format**:
```
Insights Extracted:

What We Learned:
- [Insight 1]
- [Insight 2]
- [Insight 3]

Patterns Emerged:
- [Pattern 1]
- [Pattern 2]

Questions:
- Answered: [Question 1]
- Raised: [Question 2]
```

**Output**:
- `insights`: Insights list
- `patterns`: Patterns identified
- `questions`: Questions answered and raised

#### Step 3.2: Identify Key Learnings

Identify the most important learnings:
- What are the key takeaways?
- What will user remember from this session?
- What can be applied going forward?

**Key Learnings Format**:
```
Key Learnings:

1. [Learning 1] - [Why it matters]
2. [Learning 2] - [Why it matters]
3. [Learning 3] - [Why it matters]

Applications:
- [How to apply learning 1]
- [How to apply learning 2]
...
```

**Output**:
- `key_learnings`: Key learnings list
- `applications`: Applications list

#### Step 3.3: Prepare for Writeback

Prepare user for writeback phase:
- Explain what writeback involves
- Preview what information will be collected
- Set expectations for rule generation

**Writeback Preview**:
```
Next: Writeback Phase

We'll collect:
- Your preferences (what you liked/disliked)
- State updates (how you felt)
- Generate personal rules based on today's experience

This helps build your personal dataset.
```

**Output**:
- `writeback_prepared`: Boolean
- `user_ready_for_writeback`: Boolean

### Phase 4: Writeback

**Execution Order**:
1. Step 4.0: Collect preferences
2. Step 4.1: Update states
3. Step 4.2: Generate rules
4. Step 4.3: Record session

#### Step 4.0: Collect Preferences

Collect user preferences from session:
- What did user like/dislike?
- Price sensitivity observations
- Aesthetic preferences
- Atmosphere preferences

**Preference Collection**:
```
Preference Collection:

What You Liked:
- [Preference 1]
- [Preference 2]
...

What You Disliked:
- [Dislike 1]
- [Dislike 2]
...

Price Sensitivity: [Low/Medium/High]
Aesthetic Preferences: [Preferences]
Atmosphere Preferences: [Preferences]
```

**Output**:
- `preferences`: Preferences object
- `likes`: Likes list
- `dislikes`: Dislikes list

#### Step 4.1: Update States

Update user's state map based on session:
- How did user feel during session?
- What states were experienced?
- Update state transitions

**State Updates Format**:
```
State Updates:

States Experienced:
- [State 1]: [When/Why]
- [State 2]: [When/Why]
...

State Transitions:
- [State A] → [State B]: [Trigger]
- [State B] → [State C]: [Trigger]
...
```

**Output**:
- `state_updates`: State updates object
- `states_experienced`: States experienced list
- `state_transitions`: State transitions list

#### Step 4.2: Generate Rules

Generate personal rules based on session:
- Extract rules from observations and preferences
- Generate 3-7 actionable rules
- Ensure rules are specific and applicable

**Rule Generation Format**:
```
Personal Rules Generated:

1. [Rule 1] - [Context/When to apply]
2. [Rule 2] - [Context/When to apply]
3. [Rule 3] - [Context/When to apply]
...

Rule Sources:
- Rule 1: Based on [observation/preference]
- Rule 2: Based on [observation/preference]
...
```

**Output**:
- `rules`: Rules list (3-7 rules)
- `rule_sources`: Rule sources list
- `rules_validated`: Boolean

#### Step 4.3: Record Session

Record complete session data:
- Save session summary
- Save observations and artifacts
- Save preferences, states, and rules
- Link to lens and track (if applicable)

**Session Record Format**:
```
Session Recorded:

Session ID: [session_id]
Date: [date]
Topic: [topic]
Lens: [lens_name]

Summary: [session_summary]
Observations: [observations_count]
Artifacts: [artifacts_count]
Rules Generated: [rules_count]

Status: Complete
```

**Output**:
- `session_recorded`: Boolean
- `session_id`: Session identifier
- `writeback_complete`: Boolean

## Acceptance Criteria

### Agreement Phase
- ✅ User understands session objectives
- ✅ User confirms lens perspective
- ✅ User sets personal expectations
- ✅ User agrees to session structure

### Exploration Phase
- ✅ User actively observes
- ✅ User asks questions
- ✅ User interacts with environment/participants
- ✅ Observations are collected

### Convergence Phase
- ✅ Findings are summarized
- ✅ Insights are extracted
- ✅ Key learnings are identified
- ✅ User is prepared for writeback

### Writeback Phase
- ✅ Preferences are collected
- ✅ States are updated
- ✅ Rules are generated (3-7 rules)
- ✅ Session is recorded

## Error Handling

### Preparation Errors
- If session context is missing: Prompt user to provide session_id or create new session
- If Lens Card is not found: Inform user and provide alternative options

### Agreement Errors
- If user doesn't understand objectives: Re-explain and confirm understanding
- If user doesn't agree to structure: Adjust structure or end session

### Exploration Errors
- If exploration stalls: Provide prompts and guidance
- If observations are sparse: Encourage more detailed observation

### Convergence Errors
- If findings are unclear: Help user clarify and organize
- If insights are weak: Guide user to deeper reflection

### Writeback Errors
- If preferences are incomplete: Prompt user to provide more details
- If rules cannot be generated: Use default rules or prompt for more input
- If session recording fails: Retry and inform user

## Notes

- Walk Session is a standalone session (not necessarily part of a track)
- Focus is on structured exploration and learning
- Writeback phase is critical for building personal dataset
- Rules generated should be specific and actionable
- Session can be part of Annual Track or standalone













