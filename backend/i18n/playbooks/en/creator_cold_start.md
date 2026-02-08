---
playbook_code: creator_cold_start
version: 1.0.0
capability_code: walkto_lab
name: Creator Cold Start
description: |
  Enable creators without agents/editors to complete the full flow in 1 day:
  "Lens → Week 1 Feed → 1 Cohort Session → Writeback → Portable Dataset".
  Provides low-threshold rhythm and governance fields for creators to have usable perspectives and deliverable content from day 1.
tags:
  - walkto
  - creator
  - cold-start
  - onboarding
  - lens
  - feed
  - cohort

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - walkto_create_lens_card
  - walkto_record_walk_session
  - walkto_writeback_universe
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
icon: 🚀
---

# Creator Cold Start - SOP

## Objective

Enable creators to complete the following 5 tasks in **1 day**, establishing a sustainable content delivery system:

1. **Lens Prototype Generation**: Generate initial Lens Card with 10 judgment sentences + 3 rejection rules
2. **Week 1 Feed Production**: Generate 3-5 $5 Feed drafts with consistency checks
3. **1 Cohort Hosting Session**: Complete 30-minute cohort session using simplified Walk Script
4. **Writeback & Quality Check**: Collect user preferences and generate writeback cards (with trust evidence and rule updates)
5. **Portable Dataset Prototype Export**: Export first-week Personal Dataset (Markdown/Notion format)

**Core Value**:
- Avoid vague statements like "content must be good", directly produce usable perspectives
- Provide rhythm and governance fields to prevent creators from losing pace
- Enable users to take away usable datasets on day 1

## Execution Steps

### Phase 0: Preparation

**Execution Order**:
1. Step 0.0: Collect creator basic information
2. Step 0.1: Confirm topic and material box
3. Step 0.2: Set target (Lens Feed or Annual Track)

#### Step 0.0: Collect Creator Basic Information

Ask creator:
- Your name/nickname
- Your focused topic area (e.g., coffee culture, museum exploration, mindfulness practice)
- Who is your target audience
- What value do you want to provide

**Output**:
- `creator_name`: Creator name
- `topic`: Topic area
- `target_audience`: Target audience
- `value_proposition`: Value proposition

#### Step 0.1: Confirm Topic and Material Box

Confirm if creator has:
- Prepared topic content
- Available materials (photos, notes, observations)
- Experiences or perspectives to share

If not, guide creator to prepare 3-5 specific observations or stories first.

**Output**:
- `topic_materials`: Topic material list
- `available_artifacts`: Available materials (photos, notes, etc.)

#### Step 0.2: Set Target

Confirm creator wants:
- **Option A**: Start with Lens Feed ($5/month) - Weekly perspective updates
- **Option B**: Directly do Annual Track ($29/month) - Complete co-learning track

**Output**:
- `target_tier`: "lens_feed" or "annual_track"

### Phase 1: Lens Prototype Generation

**Call sub-playbook**: `lens_prototype_generate`

Use `walkto_create_lens_card` tool to generate based on creator's topic and materials:

- **10 judgment sentences**: Specific, actionable perspectives (avoid vague statements)
- **3 rejection rules**: Clear situations not recommended/not suitable
- **Perspective model**: What the creator is most sensitive to (rhythm, atmosphere, price, etc.)

**Acceptance Criteria**:
- ✅ Judgment sentences must be specific (e.g., "This cafe is good for hiding from rain, not suitable for first-time London visitors")
- ✅ Rejection rules must be clear (e.g., "Not recommended for those who need quiet work")
- ✅ At least 3 perspectives ready for this week

**Output**:
- `lens_card`: Generated Lens Card
- `lens_id`: Lens identifier

### Phase 2: Week 1 Feed Production

**Call sub-playbook**: `week1_feed_factory`

Based on Lens Card and topic materials, generate 3-5 Feed drafts:

1. **Generate drafts**: Each contains 1-2 judgment sentences + brief observation
2. **Consistency check**: Ensure consistency with Lens Card judgment criteria
3. **Repetition check**: Avoid content repetition
4. **Safety check**: Avoid over-promising, privacy leaks, etc.
5. **Produce schedule**: Annotate publication time and order

**Acceptance Criteria**:
- ✅ At least 3 usable Feeds
- ✅ Pass consistency check
- ✅ Pass repetition check (repetition < 20%)
- ✅ Pass safety check (no risky content)

**Output**:
- `feed_drafts`: Feed draft list (3-5 items)
- `schedule`: Schedule suggestions

### Phase 3: 1 Cohort Hosting Session (if Annual Track selected)

**Only execute if `target_tier == "annual_track"`**

**Call sub-playbook**: `walk_session_host_script`

Complete 30-minute cohort session using simplified Walk Script:

1. **Opening** (5 min): Introduce topic, set expectations, risk reminders
2. **Exploration** (20 min): Guide participants to observe, ask questions, interact
3. **Wrap-up** (3 min): Summarize findings, propose next week tasks
4. **Writeback guide** (2 min): Guide participants to provide preferences and states

**Use tool**: `walkto_record_walk_session`

**Acceptance Criteria**:
- ✅ Session duration 25-35 minutes
- ✅ Complete all 4 segments (opening, exploration, wrap-up, writeback guide)
- ✅ Record at least 3 lens_notes
- ✅ Collect participant interaction traces

**Output**:
- `walk_session`: Recorded Walk Session
- `session_id`: Session identifier

### Phase 4: Quick Audience Intake + Writeback

**Merge into `personal_writeback` playbook, but use simplified flow**

Use 5 fixed questions to collect first-batch user states and preferences:

1. **State question**: What kind of experience do you want today? (quiet/social/exploration/relaxation)
2. **Preference question**: What is your price sensitivity? (low/medium/high)
3. **Aesthetic question**: What atmosphere/style do you prefer? (describe with keywords)
4. **Taboo question**: What do you absolutely dislike?
5. **Trust question**: In this experience, which moment made you feel "understood"?

**Use tool**: `walkto_writeback_universe`

**Acceptance Criteria**:
- ✅ Collect preferences from at least 3 users
- ✅ At least 1 trust evidence per user
- ✅ Generate at least 1 personal rule per user

**Output**:
- `buyer_universes`: Updated Buyer Universe list
- `writeback_cards`: Writeback card list (with trust evidence and rule updates)

### Phase 5: Writeback Card Quality Check

Check if each writeback card contains:

- ✅ **At least 1 trust evidence**: When did the user feel understood
- ✅ **At least 1 rule update**: Personal choice rules extracted from interactions
- ✅ **State mapping**: What the user prefers in what state

If not compliant, prompt creator to supplement or re-collect.

**Output**:
- `quality_report`: Quality check report
- `validated_writeback_cards`: Writeback cards that passed quality check

### Phase 6: First-Batch Dataset Prototype Export

**Use tools**: `walkto_generate_dataset` + export endpoint

Generate downloadable Personal Dataset prototype from first-week writebacks and preferences:

1. **Collect data**: Integrate all users' preferences, rules, state mappings
2. **Generate Dataset**: Use `format="markdown"` or `format="notion"`
3. **Verify completeness**: Ensure includes state_map, preferences, rules, next_steps
4. **Export**: Produce downloadable file

**Acceptance Criteria**:
- ✅ Dataset includes data from at least 3 users
- ✅ At least 3 rules per user
- ✅ At least 5 state mappings per user
- ✅ Includes next_steps (next tasks)

**Output**:
- `personal_datasets`: Generated Personal Dataset list
- `export_files`: Export files (Markdown/Notion format)

### Phase 7: "Next Steps" Reminder Script Generation

Generate two reminder message templates:

1. **24-hour reminder**:
   - Small task (10-20 minutes to complete)
   - Writeback entry link
   - Encourage completion

2. **72-hour reminder**:
   - Review this week's findings
   - Next week preview
   - Encourage continued participation

**Output**:
- `reminder_templates`: Reminder message templates
- `next_steps`: Next steps written into Dataset

### Phase 8: Risk/Forbidden Zone Rules (Hosting Safety Card)

Generate "Hosting Safety Card" including:

1. **No over-promising**: Don't promise "guaranteed effective" or "definitely suitable"
2. **Privacy protection**: Don't ask or record sensitive personal information
3. **Proxy purchase responsibility**: Clarify proxy purchase responsibility boundaries (if applicable)
4. **Content boundaries**: Don't provide medical, legal, or other professional advice

**Output**:
- `safety_card`: Hosting safety card content
- `rejection_rules_extension`: Extended rejection rules

### Phase 9: Completion Check and Next Steps

**Completion Checklist**:

- [ ] Lens Card generated and passed acceptance
- [ ] Week 1 Feed produced and passed checks (3-5 items)
- [ ] 1 cohort session completed (if Annual Track selected)
- [ ] Writeback cards generated and passed quality check
- [ ] Personal Dataset exported
- [ ] Reminder scripts generated
- [ ] Safety card provided

**Next Steps Suggestions**:

1. **Week 2**: Use `week1_feed_factory` to continue producing Feeds
2. **Week 2**: Use `walk_session_host_script` to host second cohort session
3. **Continuous writeback**: Use `personal_writeback` to update personal value systems after each session
4. **Monthly milestone**: Use `personal_dataset_export` to generate complete Dataset

---

## Tool Mapping

| Function | Tool Name | Description |
|----------|-----------|-------------|
| Lens Creation | `walkto_create_lens_card` | Create Lens Card |
| Session Recording | `walkto_record_walk_session` | Record Walk Session |
| Universe Writeback | `walkto_writeback_universe` | Writeback to Buyer Universe |
| Dataset Generation | `walkto_generate_dataset` | Generate Personal Dataset |
| Dataset Export | `/dataset/{user_id}/export` | Export Dataset |

---

## Acceptance Criteria Summary

### 1-Day Completion Check

- ✅ Lens Card generated (10 judgment sentences + 3 rejection rules)
- ✅ Week 1 Feed produced (3-5 items, passed checks)
- ✅ 1 cohort session completed (if Annual Track selected)
- ✅ Writeback cards generated (with trust evidence and rule updates)
- ✅ Personal Dataset exported (Markdown/Notion format)
- ✅ Reminder scripts generated
- ✅ Safety card provided

### Quality Thresholds

- ✅ Judgment sentences must be specific (avoid vague statements)
- ✅ Feeds pass consistency/repetition/safety checks
- ✅ Writeback cards include at least 1 trust evidence + 1 rule update
- ✅ Dataset includes at least 3 rules + 5 state mappings per user

---

**Last Updated**: 2025-12-21
**Maintainer**: Mindscape AI Team

