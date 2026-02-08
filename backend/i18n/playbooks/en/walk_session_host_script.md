---
playbook_code: walk_session_host_script
version: 1.0.0
capability_code: walkto_lab
name: Walk Session Host Script (Simplified)
description: |
  Provide 30-minute hosting script template (opening, questions, wrap-up, writeback guide) to prevent hosts from losing pace.
  Enable creators to successfully complete their first cohort session.
tags:
  - walkto
  - creator
  - walk-session
  - hosting
  - cold-start

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

# Walk Session Host Script (Simplified) - SOP

## Objective

Provide 30-minute hosting script template for creators, including:

1. **Opening** (5 min): Introduce topic, set expectations, risk reminders
2. **Exploration** (20 min): Guide participants to observe, ask questions, interact
3. **Wrap-up** (3 min): Summarize findings, propose next week tasks
4. **Writeback guide** (2 min): Guide participants to provide preferences and states

**Core Value**:
- Enable creators to maintain pace
- Prevent hosts from being unable to guide interactions
- Ensure each session has structure and output

## Execution Steps

### Phase 0: Preparation

**Execution Order**:
1. Step 0.0: Confirm topic and Lens Card
2. Step 0.1: Confirm participant list
3. Step 0.2: Prepare hosting safety card

#### Step 0.0: Confirm Topic and Lens Card

Get:
- `topic`: This session's topic
- `lens_id`: Lens identifier
- `lens_card`: Lens Card (includes judgment criteria)

**Output**:
- `topic`: Topic
- `lens_card`: Lens Card
- `judgment_criteria`: Judgment criteria (for guidance)

#### Step 0.1: Confirm Participant List

Get:
- `participants`: Participant list
- `participant_count`: Participant count

**Output**:
- `participants`: Participant list
- `participant_count`: Participant count

#### Step 0.2: Prepare Hosting Safety Card

Get or generate from `creator_cold_start` playbook:
- `safety_card`: Hosting safety card content
- `rejection_rules_extension`: Extended rejection rules

**Output**:
- `safety_card`: Safety card content
- `rejection_rules`: Rejection rules list

### Phase 1: Opening (5 minutes)

**Time Allocation**:
- 0:00-1:00: Welcome and introduction
- 1:00-2:00: Topic introduction
- 2:00-3:00: Set expectations
- 3:00-4:00: Risk reminders (safety card)
- 4:00-5:00: Confirm participant states

**Script Template**:

```
[0:00-1:00] Welcome and Introduction
"Hello everyone, I'm [Creator Name]. Today we're going to explore [Topic] together.
This is not a teaching, but a process of co-exploration. Let's try together and see what we discover."

[1:00-2:00] Topic Introduction
"Today's topic is [Topic]. I'll share some of my observations, but the focus is on exploring together.
There are no standard answers, only things we discover together."

[2:00-3:00] Set Expectations
"Today's goal is not to get perfect answers, but to:
1. Observe some interesting phenomena together
2. Share each other's experiences
3. Discover things we haven't noticed before
4. Finally, we'll organize today's discoveries into some usable rules"

[3:00-4:00] Risk Reminders (Safety Card)
"Before we start, a few reminders:
1. I won't provide medical, legal, or other professional advice
2. I won't guarantee any effects
3. This is a co-exploration, not one-way teaching
4. Your choices and experiences are your own responsibility"

[4:00-5:00] Confirm Participant States
"Before we start, I'd like to understand everyone's state:
- What kind of experience do you want today? (quiet/social/exploration/relaxation)
- What are your expectations for this topic?
- Is there anything you particularly want to explore?"
```

**Acceptance Criteria**:
- ✅ Complete all 5 segments
- ✅ Clearly set expectations (not teaching, but co-exploration)
- ✅ Complete risk reminders (safety card content)
- ✅ Collect participant states

**Output**:
- `opening_completed`: Opening completion marker
- `participant_states`: Participant state list

### Phase 2: Exploration (20 minutes)

**Time Allocation**:
- 5:00-10:00: Guide observation (10 min)
- 10:00-15:00: Questions and interaction (10 min)
- 15:00-20:00: Deep exploration (5 min)
- 20:00-25:00: Summarize observations (5 min)

**Script Template**:

```
[5:00-10:00] Guide Observation
"Now let's observe [specific scene/phenomenon] together.
Please pay attention to:
1. What do you see?
2. What do you feel?
3. What does this remind you of?

(Give participants 2-3 minutes to observe, then share)

Based on my Lens, I notice:
- [Judgment sentence 1]
- [Judgment sentence 2]
- [Judgment sentence 3]

Do you have different observations?"

[10:00-15:00] Questions and Interaction
"I'd like to ask everyone a few questions:
1. What does this scene/phenomenon mean to you?
2. In what state would you need this?
3. Who do you think is not suitable for this?

(Guide participants to answer, record key responses)

Based on everyone's responses, I found:
- [Observation 1]
- [Observation 2]
- [Observation 3]"

[15:00-20:00] Deep Exploration
"Let's go deeper:
- If we change perspective, how would you see it?
- How can this discovery be applied to your life?
- What else do you think is worth exploring?"

[20:00-25:00] Summarize Observations
"Let's summarize today's discoveries:
1. [Discovery 1]
2. [Discovery 2]
3. [Discovery 3]

How can these discoveries be used? We'll organize them into some usable rules next."
```

**Acceptance Criteria**:
- ✅ Complete all 4 segments
- ✅ Guide participants to observe and interact
- ✅ Record at least 3 lens_notes
- ✅ Collect participant interaction traces

**Output**:
- `lens_notes`: This session's Lens Notes (at least 3)
- `participant_interactions`: Participant interaction records
- `key_observations`: Key observation list

### Phase 3: Wrap-up (3 minutes)

**Time Allocation**:
- 25:00-27:00: Summarize findings
- 27:00-28:00: Propose next week tasks

**Script Template**:

```
[25:00-27:00] Summarize Findings
"Let's summarize today's discoveries:

1. [Discovery 1] - This means [meaning]
2. [Discovery 2] - This means [meaning]
3. [Discovery 3] - This means [meaning]

How can these discoveries be used? We'll organize them into some usable rules and write them into your personal dataset."

[27:00-28:00] Propose Next Week Tasks
"Next week we'll continue exploring [next week's topic].
Before we meet again, you can try:
- [Small task 1] (10-20 minutes)
- [Small task 2] (optional)

After completion, you can tell me your discoveries through the writeback entry. We'll organize these discoveries into your personal dataset."
```

**Acceptance Criteria**:
- ✅ Summarize at least 3 findings
- ✅ Propose at least 1 next week task
- ✅ Clearly state will be organized into personal dataset

**Output**:
- `session_summary`: This session's summary
- `next_week_tasks`: Next week task list

### Phase 4: Writeback Guide (2 minutes)

**Time Allocation**:
- 28:00-29:00: Guide to provide preferences
- 29:00-30:00: Guide to provide trust evidence

**Script Template**:

```
[28:00-29:00] Guide to Provide Preferences
"Before we end, I'd like to understand your preferences:
1. In what state did you participate today? (quiet/social/exploration/relaxation)
2. What is your price sensitivity? (low/medium/high)
3. What atmosphere/style do you prefer? (describe with keywords)
4. What do you absolutely dislike?

This information will help me better understand you and provide more suitable recommendations in the future."

[29:00-30:00] Guide to Provide Trust Evidence
"One last question:
In today's exploration, which moment made you feel 'understood' or 'resonated'?

This will help me understand what kind of content is most valuable to you, and we'll record this in your trust evidence library."
```

**Acceptance Criteria**:
- ✅ Collect preferences from at least 3 participants
- ✅ Collect at least 1 trust evidence
- ✅ Clearly state will be recorded in personal dataset

**Output**:
- `participant_preferences`: Participant preference list
- `trust_evidence`: Trust evidence list

### Phase 5: Record Walk Session

**Use tool**: `walkto_record_walk_session`

**Input Parameters**:
- `lens_id`: Lens identifier
- `route_map`: This session's route/rhythm (extracted from script)
- `lens_notes`: This session's Lens Notes (at least 3)
- `shared_artifacts`: Shared materials (photos, notes, etc.)
- `duration_minutes`: 30

**Acceptance Criteria**:
- ✅ Session recorded successfully
- ✅ Includes at least 3 lens_notes
- ✅ Includes participant interaction traces
- ✅ Duration 25-35 minutes

**Output**:
- `walk_session`: Recorded Walk Session
- `session_id`: Session identifier

### Phase 6: Generate Writeback Cards (Merge into personal_writeback)

**Use tool**: `walkto_writeback_universe`

**Input Parameters**:
- `user_id`: Participant ID
- `session_id`: Session ID
- `preferences`: Participant preferences
- `trust_evidence`: Trust evidence
- `state_updates`: State updates

**Acceptance Criteria**:
- ✅ Writeback card includes at least 1 trust evidence
- ✅ Writeback card includes at least 1 rule update
- ✅ Writeback card includes state mapping

**Output**:
- `writeback_cards`: Writeback card list

---

## Acceptance Criteria Summary

### Must Achieve

- ✅ Complete 30-minute hosting (opening 5 min + exploration 20 min + wrap-up 3 min + writeback guide 2 min)
- ✅ Complete all 4 phases
- ✅ Record at least 3 lens_notes
- ✅ Collect participant interaction traces
- ✅ Generate writeback cards (with trust evidence and rule updates)

### Quality Thresholds

- ✅ Clearly set expectations (not teaching, but co-exploration)
- ✅ Complete risk reminders (safety card content)
- ✅ Guide participants to observe and interact
- ✅ Summarize at least 3 findings
- ✅ Propose at least 1 next week task

---

**Last Updated**: 2025-12-21
**Maintainer**: Mindscape AI Team

