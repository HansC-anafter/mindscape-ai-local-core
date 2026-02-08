---
playbook_code: week1_feed_factory
version: 1.0.0
capability_code: walkto_lab
name: Week 1 Feed Factory
description: |
  Given topic and material box, generate 3-5 $5 Feed drafts.
  Automatically perform consistency/repetition/safety checks, produce scheduled drafts.
  Enable creators to have publishable content from week 1.
tags:
  - walkto
  - creator
  - feed
  - content-generation
  - cold-start

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - cloud_capability.call
  - filesystem_write_file

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 📝
---

# Week 1 Feed Factory - SOP

## Objective

Generate first-week Feed content (3-5 items) for creators, including:

1. **Generate drafts**: Based on Lens Card and topic materials, generate 3-5 Feed drafts
2. **Consistency check**: Ensure consistency with Lens Card judgment criteria
3. **Repetition check**: Avoid content repetition (repetition < 20%)
4. **Safety check**: Avoid over-promising, privacy leaks, etc.
5. **Produce schedule**: Annotate publication time and order

**Core Value**:
- Enable creators to have publishable content from week 1
- Ensure content quality and consistency
- Avoid risky content

## Execution Steps

### Phase 0: Prepare Input Data

**Execution Order**:
1. Step 0.0: Get Lens Card
2. Step 0.1: Collect topic materials
3. Step 0.2: Confirm target audience

#### Step 0.0: Get Lens Card

Get from `creator_cold_start` playbook or direct input:
- `lens_id`: Lens identifier
- `lens_card`: Lens Card object (includes judgment_criteria, rejection_rules)

**Output**:
- `lens_card`: Lens Card object
- `judgment_criteria`: Judgment criteria list
- `rejection_rules`: Rejection rules list

#### Step 0.1: Collect Topic Materials

Collect materials prepared by creator:
- Photos, notes, observation records
- Specific stories or cases
- Perspectives to share

**Output**:
- `topic_materials`: Topic material list
- `available_artifacts`: Available materials (photos, notes, etc.)

#### Step 0.2: Confirm Target Audience

Confirm Feed's target audience:
- Who will read this Feed?
- What do they want?
- In what state do they need this content?

**Output**:
- `target_audience`: Target audience description
- `audience_needs`: Audience needs list

### Phase 1: Generate Feed Drafts

**Generation Logic**:

1. **Based on Lens Card judgment sentences**: Select 3-5 from `feed_ready_sentences`
2. **Combine with topic materials**: Pair each judgment sentence with specific stories or cases
3. **Generate Feed content**: Each includes:
   - 1-2 judgment sentences (perspectives)
   - Brief observation or story (50-100 words)
   - Optional: Photo or material link

**Generation Example**:

```
Feed 1:
Perspective: "This cafe is good for hiding from rain, not suitable for first-time London visitors"
Observation: It rained today, walked into this cafe. The interior is warm, suitable for long stays. But if you're visiting London for the first time, you might find the location hard to find.
Material: [Photo: Interior environment]

Feed 2:
Perspective: "This cafe is suitable for those who need quiet work, not suitable for those who want to socialize"
Observation: The cafe is very quiet, everyone is working or reading. If you want to chat with someone, this is not the place.
Material: [Photo: Work scene]
```

**Acceptance Criteria**:
- ✅ Generate at least 3 Feed drafts
- ✅ Each includes at least 1 judgment sentence
- ✅ Each includes brief observation or story
- ✅ Content based on actual materials (not imagined)

**Output**:
- `feed_drafts`: Feed draft list (3-5 items)

### Phase 2: Consistency Check

**Check Logic**:

1. **Judgment criteria consistency**: Ensure judgment sentences in Feed match Lens Card's judgment_criteria
2. **Rejection rules consistency**: Ensure Feed doesn't violate rejection_rules
3. **Perspective model consistency**: Ensure Feed's perspectives match perspective_model

**Check Items**:

- ✅ Are judgment sentences in Feed within Lens Card's judgment_criteria?
- ✅ Does Feed violate any rejection_rules?
- ✅ Do Feed's perspectives match perspective_model's sensitivities?

**Acceptance Criteria**:
- ✅ All Feeds pass consistency check
- ✅ No content violating rejection_rules
- ✅ Perspectives match perspective_model

**Output**:
- `consistency_report`: Consistency check report
- `validated_feeds`: Feeds that passed check

### Phase 3: Repetition Check

**Check Logic**:

1. **Content repetition**: Calculate content similarity between Feeds
2. **Judgment sentence repetition**: Check for duplicate judgment sentences
3. **Story repetition**: Check for duplicate stories or cases

**Check Method**:

Use text similarity calculation (e.g., cosine similarity):
- Calculate similarity between each pair of Feeds
- If similarity > 20%, mark as repetitive

**Acceptance Criteria**:
- ✅ Repetition between all Feeds < 20%
- ✅ No completely duplicate judgment sentences
- ✅ No completely duplicate stories

**Output**:
- `repetition_report`: Repetition check report
- `deduplicated_feeds`: Deduplicated Feed list

### Phase 4: Safety Check

**Check Items**:

1. **Over-promising**:
   - ❌ "Guaranteed effective"
   - ❌ "Definitely suitable"
   - ❌ "Absolutely recommended"
   - ✅ "May be suitable" "Worth trying"

2. **Privacy risks**:
   - ❌ Specific addresses, phone numbers, personal information
   - ✅ Vague location descriptions ("some area" "nearby")

3. **Professional advice**:
   - ❌ Medical advice
   - ❌ Legal advice
   - ❌ Financial advice
   - ✅ Personal experience sharing

4. **Proxy purchase responsibility**:
   - ❌ "Guaranteed to buy"
   - ❌ "Absolutely authentic"
   - ✅ "Can help check" "Need to confirm"

**Check Logic**:

Use keyword matching + LLM semantic check:
- Check if contains forbidden keywords
- Use LLM to check if semantics are over-promising

**Acceptance Criteria**:
- ✅ No over-promising content
- ✅ No privacy risks
- ✅ No professional advice (unless explicitly labeled)
- ✅ No proxy purchase responsibility risks

**Output**:
- `safety_report`: Safety check report
- `safe_feeds`: Feeds that passed check

### Phase 5: Produce Schedule

**Schedule Suggestions**:

1. **Publication frequency**: 1-2 items per week (suggest Monday, Thursday)
2. **Publication time**: Based on target audience active time (suggest 09:00 or 18:00)
3. **Publication order**: Publish more general content first, then more specialized content

**Schedule Format**:

```markdown
## Week 1 Feed Schedule

### Feed 1: [Title]
- Publication time: Monday 09:00
- Perspective: [Judgment sentence]
- Content: [Observation/story]
- Material: [Photo/link]

### Feed 2: [Title]
- Publication time: Thursday 18:00
- Perspective: [Judgment sentence]
- Content: [Observation/story]
- Material: [Photo/link]

...
```

**Acceptance Criteria**:
- ✅ At least 3 Feeds have clear schedule
- ✅ Publication times are reasonable (consider audience active time)
- ✅ Publication order is logical (general first, then specialized)

**Output**:
- `schedule`: Schedule suggestions
- `scheduled_feeds`: Scheduled Feed list

### Phase 6: Final Check and Output

**Final Checklist**:

- [ ] At least 3 Feed drafts
- [ ] Passed consistency check
- [ ] Passed repetition check (repetition < 20%)
- [ ] Passed safety check
- [ ] Schedule generated

**Output Files**:

1. **Feed draft file**: `week1_feeds_draft.md`
2. **Schedule file**: `week1_feeds_schedule.md`
3. **Check report**: `week1_feeds_quality_report.md`

---

## Acceptance Criteria Summary

### Must Achieve

- ✅ Generate at least 3 Feed drafts
- ✅ Pass consistency check (consistent with Lens Card)
- ✅ Pass repetition check (repetition < 20%)
- ✅ Pass safety check (no risky content)
- ✅ Produce schedule (publication time and order)

### Quality Thresholds

- ✅ Each Feed includes at least 1 judgment sentence
- ✅ Each Feed includes brief observation or story
- ✅ Content based on actual materials (not imagined)
- ✅ No over-promising, privacy risks, professional advice, proxy purchase responsibility

---

**Last Updated**: 2025-12-21
**Maintainer**: Mindscape AI Team













