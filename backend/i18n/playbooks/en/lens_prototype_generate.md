---
playbook_code: lens_prototype_generate
version: 1.0.0
capability_code: walkto_lab
name: Lens Prototype Generation
description: |
  Generate initial Lens Card with 10 judgment sentences + 3 rejection rules, and produce 3 usable perspectives for this week.
  Avoid vague statements like "content must be good", directly produce specific, actionable perspective models.
tags:
  - walkto
  - creator
  - lens
  - prototype
  - cold-start

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - walkto_create_lens_card
  - cloud_capability.call

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🔍
---

# Lens Prototype Generation - SOP

## Objective

Generate initial Lens Card for creators, including:

1. **10 judgment sentences**: Specific, actionable perspectives (avoid vague statements)
2. **3 rejection rules**: Clear situations not recommended/not suitable
3. **Perspective model**: What the creator is most sensitive to (rhythm, atmosphere, price, cultural context, etc.)
4. **This week's usable perspectives**: At least 3 perspectives ready for immediate Feed use

**Core Value**:
- Enable creators to have usable perspectives from day 1
- Avoid vague statements like "content must be good"
- Establish sustainable judgment criteria

## Execution Steps

### Phase 0: Collect Creator Perspective Materials

**Execution Order**:
1. Step 0.0: Collect creator's topic and experiences
2. Step 0.1: Extract creator's sensitivities
3. Step 0.2: Collect creator's judgment criteria

#### Step 0.0: Collect Creator's Topic and Experiences

Ask creator:
- What topic do you focus on? (e.g., London coffee culture, museum exploration, mindfulness practice)
- What specific experiences do you have in this topic?
- What interesting phenomena or patterns have you observed?
- What do you think is the most misunderstood aspect of this topic?

**Output**:
- `topic`: Topic area
- `experiences`: Specific experience list
- `observations`: Observed phenomena
- `misconceptions`: Common misconceptions

#### Step 0.1: Extract Creator's Sensitivities

Ask creator:
- What are you most sensitive to in this topic? (rhythm, atmosphere, price, cultural context, crowd type, etc.)
- What makes you immediately judge "this is not suitable"?
- What makes you feel "this is worth recommending"?

**Output**:
- `sensitivities`: Sensitivity list
- `rejection_triggers`: Rejection trigger conditions
- `recommendation_criteria`: Recommendation criteria

#### Step 0.2: Collect Creator's Judgment Criteria

Ask creator:
- What criteria do you use to judge "this is suitable/not suitable for whom"?
- What situations do you refuse to recommend?
- What extra steps are you willing to take for your audience?

**Output**:
- `judgment_criteria`: Judgment criteria list
- `rejection_rules_draft`: Rejection rules draft
- `extra_steps`: Extra steps list

### Phase 1: Generate 10 Judgment Sentences

**Requirements**:
- Must be specific and actionable (avoid vague statements)
- Must include judgment of "suitable for whom/not suitable for whom"
- Must be based on creator's actual experiences

**Generation Examples**:

❌ **Vague Examples** (avoid):
- "This cafe is good"
- "This exhibition is worth seeing"
- "This practice is effective"

✅ **Specific Examples** (adopt):
- "This cafe is good for hiding from rain, not suitable for first-time London visitors"
- "This exhibition is suitable for those who want quiet reflection, not suitable for families with children"
- "This mindfulness practice is suitable for morning after waking up, not suitable before sleep"

**Generation Logic**:

1. Based on creator's experiences and observations
2. Combined with sensitivities (rhythm, atmosphere, price, etc.)
3. Clearly identify suitable/not suitable audiences
4. Include specific contexts or conditions

**Acceptance Criteria**:
- ✅ At least 10 judgment sentences
- ✅ Each sentence is specific (not vague)
- ✅ Each sentence includes "suitable for whom/not suitable for whom"
- ✅ At least 3 ready for this week's Feed

**Output**:
- `judgment_sentences`: List of 10 judgment sentences
- `feed_ready_sentences`: This week's usable perspectives (at least 3)

### Phase 2: Generate 3 Rejection Rules

**Requirements**:
- Must be clear and verifiable
- Must be based on creator's actual experiences
- Must be a trust source (why reject)

**Generation Examples**:

❌ **Vague Examples** (avoid):
- "Not recommended for everyone"
- "Not suitable for certain situations"

✅ **Clear Examples** (adopt):
- "Not recommended for those who need quiet work (because the environment is noisy)"
- "Not suitable for first-time London visitors (because it requires local knowledge)"
- "Not recommended for those with limited budgets (because the price is higher)"

**Generation Logic**:

1. Based on creator's rejection trigger conditions
2. Clearly identify rejected audiences and reasons
3. Explain why this is a trust source

**Acceptance Criteria**:
- ✅ At least 3 rejection rules
- ✅ Each rule is clear (not vague)
- ✅ Each rule includes rejection reason

**Output**:
- `rejection_rules`: List of 3 rejection rules

### Phase 3: Build Perspective Model

**Perspective Model Structure**:

```python
perspective_model = {
    "sensitivities": [
        "Rhythm (fast/slow)",
        "Atmosphere (quiet/lively)",
        "Price (low/medium/high)",
        "Cultural context (local/international)"
    ],
    "judgment_focus": "When to enter/not enter",
    "filter_priority": ["Suitable for whom", "Not suitable for whom", "Why"]
}
```

**Generation Logic**:

1. Based on creator's sensitivities
2. Define judgment focus (what the creator cares most about)
3. Define filter priority (how the creator makes choices)

**Acceptance Criteria**:
- ✅ Includes at least 3 sensitivities
- ✅ Judgment focus is clear
- ✅ Filter priority is clear

**Output**:
- `perspective_model`: Perspective model dictionary

### Phase 4: Generate Extra Steps (Optional)

Ask creator:
- What extra steps are you willing to take for your audience?
- What additional value will you provide?

**Output**:
- `extra_steps`: Extra steps list (optional)

### Phase 5: Create Lens Card

**Use tool**: `walkto_create_lens_card`

**Input Parameters**:
- `lens_name`: Creator name
- `perspective_model`: Perspective model
- `judgment_criteria`: 10 judgment sentences
- `rejection_rules`: 3 rejection rules
- `extra_steps`: Extra steps (optional)

**Acceptance Criteria**:
- ✅ Lens Card created successfully
- ✅ Includes all required fields
- ✅ Passes Lens consistency check

**Output**:
- `lens_card`: Created Lens Card
- `lens_id`: Lens identifier

### Phase 6: Produce This Week's Usable Perspectives

Select at least 3 perspectives from the 10 judgment sentences that can be directly used for this week's Feed:

**Selection Criteria**:
- Specific and actionable
- Supported by actual cases or stories
- Can resonate with target audience

**Output**:
- `feed_ready_sentences`: This week's usable perspectives (at least 3)
- `feed_suggestions`: Feed content suggestions

---

## Acceptance Criteria

### Must Achieve

- ✅ Generate at least 10 judgment sentences (each specific and actionable)
- ✅ Generate at least 3 rejection rules (each clear and verifiable)
- ✅ Build complete perspective model (at least 3 sensitivities)
- ✅ Create Lens Card successfully
- ✅ Produce at least 3 usable perspectives for this week

### Quality Thresholds

- ✅ Judgment sentences are not vague (have specific contexts, audiences, conditions)
- ✅ Rejection rules are clear (have specific reasons)
- ✅ Perspective model is complete (includes sensitivities, judgment focus, filter priority)

---

**Last Updated**: 2025-12-21
**Maintainer**: Mindscape AI Team













