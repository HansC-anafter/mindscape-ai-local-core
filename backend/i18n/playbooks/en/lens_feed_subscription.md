---
playbook_code: lens_feed_subscription
version: 1.0.0
capability_code: walkto_lab
name: Lens Feed Subscription
description: |
  Subscribe to a Lens Feed ($5/month) to receive weekly perspective updates,
  monthly playbook summaries, and access to material-based Q&A.
  Follow a worldview as it evolves continuously.
tags:
  - walkto
  - subscription
  - lens
  - feed
  - weekly-updates

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - cloud_capability.call

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 📰
---

# Lens Feed Subscription - SOP

## Objective

Enable users to subscribe to and interact with Lens Feed ($5/month), providing:

1. **Weekly Perspective Updates**: Receive 3-7 judgment sentences and observations every week
2. **Monthly Playbook Summary**: Receive a monthly summary of perspectives and patterns
3. **Material-Based Q&A**: Ask questions based on the creator's material library (not generic AI)

**Core Value**:
- Follow a worldview as it evolves continuously
- Access curated perspectives without personalization commitment
- Low-cost entry point to explore a creator's lens

**What It Does NOT Guarantee**:
- Personalization (content is not tailored to individual users)
- Completion tracking (no progress monitoring)
- Memory (system does not remember your preferences)

## Execution Steps

### Phase 0: Subscription Setup

**Execution Order**:
1. Step 0.0: Identify target Lens
2. Step 0.1: Check existing subscription status
3. Step 0.2: Create or activate subscription

#### Step 0.0: Identify Target Lens

Ask user:
- Which creator's Lens do you want to subscribe to?
- Do you have a specific lens_id?
- Or do you want to browse available Lenses?

**Output**:
- `lens_id`: Target Lens identifier
- `lens_name`: Lens name (IP/creator name)

#### Step 0.1: Check Existing Subscription Status

Check if user already has an active Lens Feed subscription:
- Query subscription service for user_id and tier="lens_feed"
- Check if subscription is active and not expired

**Output**:
- `has_active_subscription`: Boolean
- `existing_subscription`: Subscription object (if exists)
- `subscription_status`: "active" | "cancelled" | "expired" | "none"

#### Step 0.2: Create or Activate Subscription

If no active subscription:
1. Create new subscription via subscription service
2. Set tier to "lens_feed"
3. Set expiration to 30 days from now
4. Process payment (if required)

If subscription exists but expired:
1. Renew subscription
2. Update expiration date
3. Process payment (if required)

If subscription is active:
1. Confirm subscription is active
2. Proceed to Phase 1

**Output**:
- `subscription_id`: Subscription identifier
- `subscription_status`: "active"
- `expires_at`: Expiration timestamp

### Phase 1: View Weekly Updates

**Execution Order**:
1. Step 1.0: Get latest weekly update
2. Step 1.1: Display update content
3. Step 1.2: Check update history

#### Step 1.0: Get Latest Weekly Update

Query Lens Feed service for latest weekly update:
- Get update for current week (Monday 00:00 UTC)
- If no update for current week, get most recent update
- Include judgment sentences, observations, and optional materials

**Output**:
- `weekly_update`: Weekly update object
- `update_date`: Update timestamp
- `judgment_sentences`: List of 3-7 judgment sentences
- `observations`: List of observations or stories
- `materials`: Optional photos, notes, or links

#### Step 1.1: Display Update Content

Present weekly update to user:
- Format: Judgment sentences + brief observations
- Include optional materials (photos, notes)
- Show update date and week number

**Display Format**:
```
Week [N] Update - [Lens Name]
Date: [YYYY-MM-DD]

Perspectives:
1. [Judgment sentence 1]
   [Brief observation or story]

2. [Judgment sentence 2]
   [Brief observation or story]

...

Materials: [Photo/Note links if available]
```

**Acceptance Criteria**:
- ✅ Update content is displayed clearly
- ✅ Judgment sentences are numbered
- ✅ Observations are paired with judgment sentences
- ✅ Materials are accessible (if available)

#### Step 1.2: Check Update History

If user requests, show previous weekly updates:
- List updates from past 4 weeks
- Allow user to view specific week's update
- Show update dates and week numbers

**Output**:
- `update_history`: List of past weekly updates
- `total_updates`: Total number of updates available

### Phase 2: Material-Based Q&A

**Execution Order**:
1. Step 2.0: Collect user question
2. Step 2.1: Search material library
3. Step 2.2: Generate answer based on materials

#### Step 2.0: Collect User Question

Ask user:
- What would you like to know about [Lens topic]?
- Be specific about what you're looking for
- Context: Are you planning a visit? Looking for recommendations?

**Output**:
- `user_question`: User's question text
- `question_context`: Optional context about user's situation

#### Step 2.1: Search Material Library

Search creator's material library for relevant content:
- Search by keywords from user question
- Match against judgment sentences, observations, and materials
- Filter by relevance and recency

**Search Logic**:
- Use semantic search if available
- Match keywords in judgment sentences
- Match keywords in observation stories
- Prioritize recent materials

**Output**:
- `relevant_materials`: List of relevant materials
- `matched_judgment_sentences`: Matching judgment sentences
- `matched_observations`: Matching observations

#### Step 2.2: Generate Answer Based on Materials

Generate answer using only material library content:
- Base answer on matched judgment sentences and observations
- Do NOT use generic AI knowledge
- Cite specific materials when possible
- If no relevant materials found, inform user

**Answer Format**:
```
Based on [Lens Name]'s perspective:

[Answer based on judgment sentences and observations]

Relevant materials:
- [Material 1 reference]
- [Material 2 reference]

Note: This answer is based on the creator's material library, not generic AI knowledge.
```

**Acceptance Criteria**:
- ✅ Answer is based on material library only
- ✅ No generic AI knowledge is used
- ✅ Materials are cited when possible
- ✅ If no materials found, user is informed

### Phase 3: Monthly Playbook Summary

**Execution Order**:
1. Step 3.0: Check if monthly summary is available
2. Step 3.1: Generate or retrieve monthly summary
3. Step 3.2: Display summary

#### Step 3.0: Check if Monthly Summary is Available

Check if monthly summary exists for current month:
- Query for summary of current month
- If not available, check if it's time to generate (first day of month)
- If not time yet, inform user when summary will be available

**Output**:
- `summary_available`: Boolean
- `summary_date`: Summary timestamp
- `next_summary_date`: When next summary will be available

#### Step 3.1: Generate or Retrieve Monthly Summary

If summary exists:
- Retrieve existing monthly summary
- Include patterns, trends, and key perspectives

If summary needs to be generated:
- Aggregate all weekly updates from past month
- Identify patterns and trends
- Extract key perspectives
- Generate summary document

**Summary Content**:
- Overview of month's perspectives
- Patterns and trends observed
- Key judgment sentences
- Notable observations or stories
- Material highlights

**Output**:
- `monthly_summary`: Monthly summary object
- `summary_content`: Summary text
- `patterns`: List of identified patterns
- `key_perspectives`: List of key perspectives

#### Step 3.2: Display Summary

Present monthly summary to user:
- Format as readable document
- Include patterns and trends
- Highlight key perspectives
- Show material highlights

**Display Format**:
```
Monthly Summary - [Lens Name]
Month: [YYYY-MM]

Overview:
[Summary of month's perspectives and patterns]

Key Perspectives:
1. [Perspective 1]
2. [Perspective 2]
...

Patterns & Trends:
- [Pattern 1]
- [Pattern 2]
...

Material Highlights:
- [Material 1]
- [Material 2]
...
```

**Acceptance Criteria**:
- ✅ Summary is clearly formatted
- ✅ Patterns and trends are identified
- ✅ Key perspectives are highlighted
- ✅ Material highlights are included

### Phase 4: Subscription Management

**Execution Order**:
1. Step 4.0: Check subscription status
2. Step 4.1: Handle renewal or cancellation
3. Step 4.2: Update subscription preferences

#### Step 4.0: Check Subscription Status

Query current subscription status:
- Check if subscription is active
- Check expiration date
- Check payment status

**Output**:
- `subscription_status`: "active" | "expiring_soon" | "expired" | "cancelled"
- `days_until_expiration`: Days until expiration
- `payment_status`: Payment status

#### Step 4.1: Handle Renewal or Cancellation

If user wants to renew:
1. Process payment (if required)
2. Update expiration date
3. Confirm renewal

If user wants to cancel:
1. Update subscription status to "cancelled"
2. Confirm cancellation
3. Inform user about access until expiration

**Output**:
- `action_taken`: "renewed" | "cancelled" | "none"
- `new_expiration_date`: Updated expiration date (if renewed)

#### Step 4.2: Update Subscription Preferences

If user wants to change preferences:
- Update notification preferences
- Update delivery preferences
- Save preferences

**Output**:
- `preferences_updated`: Boolean
- `updated_preferences`: Updated preferences object

## Acceptance Criteria

### Subscription Setup
- ✅ User can subscribe to Lens Feed
- ✅ Subscription is created with correct tier ("lens_feed")
- ✅ Payment is processed (if required)
- ✅ Subscription expiration is set correctly (30 days)

### Weekly Updates
- ✅ User can view latest weekly update
- ✅ Update contains 3-7 judgment sentences
- ✅ Update includes observations or stories
- ✅ User can view update history

### Material-Based Q&A
- ✅ User can ask questions
- ✅ Answers are based on material library only
- ✅ No generic AI knowledge is used
- ✅ Materials are cited when possible

### Monthly Summary
- ✅ Monthly summary is available on first day of month
- ✅ Summary includes patterns and trends
- ✅ Summary highlights key perspectives
- ✅ Summary includes material highlights

### Subscription Management
- ✅ User can check subscription status
- ✅ User can renew subscription
- ✅ User can cancel subscription
- ✅ User can update preferences

## Error Handling

### Subscription Errors
- If subscription creation fails: Inform user and retry
- If payment fails: Inform user and provide alternative payment methods
- If subscription expired: Prompt user to renew

### Update Errors
- If no weekly update available: Inform user when next update will be available
- If update retrieval fails: Retry and inform user

### Q&A Errors
- If no relevant materials found: Inform user and suggest alternative questions
- If search fails: Retry and inform user

### Summary Errors
- If summary generation fails: Retry and inform user
- If summary not available: Inform user when it will be available

## Notes

- Lens Feed is a low-cost entry point ($5/month)
- Content is not personalized to individual users
- System does not track user progress or preferences
- Focus is on following a worldview as it evolves
- Monthly summaries help users see patterns over time













