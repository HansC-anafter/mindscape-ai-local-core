---
playbook_code: annual_track_cohort
version: 1.0.0
capability_code: walkto_lab
name: Annual Track Cohort
description: |
  Subscribe to Annual Track ($29/month or $290/year) to join a cohort and be accompanied
  in living a worldview into life. Includes weekly co-learning sessions, writeback cards,
  monthly milestones, and final Personal Dataset delivery.
tags:
  - walkto
  - subscription
  - cohort
  - annual-track
  - co-learning

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
icon: 🎯
---

# Annual Track Cohort - SOP

## Objective

Enable users to subscribe to and participate in Annual Track ($29/month or $290/year), providing:

1. **Weekly Co-learning Sessions**: 60-90 minute sessions with exploration and convergence
2. **Weekly Writeback Cards**: Personal preference and rule extraction after each session
3. **Weekly Dataset Increments**: Personal dataset grows each week
4. **Monthly Milestones**: Progress checkpoints with completion review
5. **Final Personal Dataset**: Complete portable life dataset after 12 weeks

**Core Value**:
- Be accompanied in living a worldview into life
- Transform uncertain processes into completable practices
- Take away your own method and rules

**Standard Structure**:
- **Weekly Rhythm**: Co-learning Session + Writeback Card + Dataset Increment
- **Monthly Milestone**: Completion checkpoint
- **Final Delivery**: Personal Dataset (portable life dataset)

## Execution Steps

### Phase 0: Subscription and Cohort Join

**Execution Order**:
1. Step 0.0: Identify target Track
2. Step 0.1: Check existing subscription status
3. Step 0.2: Create or activate Annual Track subscription
4. Step 0.3: Join or create Cohort

#### Step 0.0: Identify Target Track

Ask user:
- Which Annual Track do you want to join?
- Do you have a specific track_id?
- Or do you want to browse available Tracks?

**Track Types**:
- Annual reading (e.g., Zizhi Tongjian, Feynman, Behavioral Economics)
- Annual physical practice (e.g., RYT 200)
- Annual mental practice (e.g., Mindfulness 100 hours)
- Annual cultural practice (e.g., City/Coffee/Museum exploration)

**Output**:
- `track_id`: Target Track identifier
- `track_name`: Track name
- `track_type`: Track type
- `lens_id`: Associated Lens identifier

#### Step 0.1: Check Existing Subscription Status

Check if user already has an active Annual Track subscription:
- Query subscription service for user_id and tier="annual_track"
- Check if subscription is active and not expired
- Check if subscription is associated with a track

**Output**:
- `has_active_subscription`: Boolean
- `existing_subscription`: Subscription object (if exists)
- `subscription_status`: "active" | "cancelled" | "expired" | "none"
- `associated_track_id`: Associated track ID (if exists)

#### Step 0.2: Create or Activate Annual Track Subscription

If no active subscription:
1. Create new subscription via subscription service
2. Set tier to "annual_track"
3. Set expiration to 30 days from now (monthly) or 365 days from now (yearly)
4. Associate subscription with track_id
5. Process payment (if required)

If subscription exists but expired:
1. Renew subscription
2. Update expiration date
3. Process payment (if required)

If subscription is active:
1. Confirm subscription is active
2. Proceed to Step 0.3

**Output**:
- `subscription_id`: Subscription identifier
- `subscription_status`: "active"
- `expires_at`: Expiration timestamp
- `track_id`: Associated track ID

#### Step 0.3: Join or Create Cohort

If cohort exists for this track:
1. Check cohort capacity
2. Add user to cohort
3. Set user's start date
4. Initialize user's weekly progress tracking

If cohort doesn't exist:
1. Create new cohort for this track
2. Set cohort capacity (e.g., 10-20 participants)
3. Add user as first participant
4. Set cohort start date
5. Initialize cohort schedule

**Output**:
- `cohort_id`: Cohort identifier
- `cohort_name`: Cohort name
- `participant_count`: Current participant count
- `user_start_date`: User's start date in cohort
- `cohort_schedule`: Weekly session schedule

### Phase 1: Weekly Rhythm Management

**Execution Order**:
1. Step 1.0: Check current week status
2. Step 1.1: Attend or review weekly session
3. Step 1.2: Complete writeback card
4. Step 1.3: Update personal dataset increment

#### Step 1.0: Check Current Week Status

Query user's current week status:
- Get current week number (1-12)
- Check if weekly session is scheduled
- Check if writeback card is completed
- Check if dataset increment is updated

**Output**:
- `current_week`: Current week number (1-12)
- `session_status`: "scheduled" | "completed" | "missed" | "none"
- `writeback_status`: "pending" | "completed" | "none"
- `dataset_status`: "pending" | "updated" | "none"

#### Step 1.1: Attend or Review Weekly Session

If session is scheduled:
1. Provide session details (time, location, topic)
2. Send reminder if session is upcoming
3. Guide user to attend session
4. After session, record session data

If session is completed:
1. Show session summary
2. Show session artifacts (photos, notes, observations)
3. Guide user to complete writeback card

If session was missed:
1. Inform user about missed session
2. Provide make-up options (if available)
3. Update progress tracking

**Session Structure** (60-90 minutes):
- **Exploration Phase** (30-45 min): Guided observation, questions, interaction
- **Convergence Phase** (20-30 min): Summarize findings, extract insights
- **Wrap-up** (10-15 min): Propose next week tasks, set expectations

**Output**:
- `session_id`: Session identifier
- `session_date`: Session date
- `session_summary`: Session summary
- `session_artifacts`: Session artifacts (photos, notes, observations)
- `lens_notes`: Lens notes extracted from session

#### Step 1.2: Complete Writeback Card

After each session, guide user to complete writeback card:
1. Collect user preferences (what user liked/disliked)
2. Extract state updates (when user felt what)
3. Generate personal rules (3-7 rules based on session)
4. Collect trust evidence (when user felt understood)

**Writeback Card Content**:
- **Preferences**: Price sensitivity, aesthetic preferences, atmosphere preferences
- **State Updates**: State map updates (e.g., "quiet" → "cozy_cafe")
- **Rules**: Personal choice rules (e.g., "Avoid noisy places when working")
- **Trust Evidence**: Moments when user felt understood

**Output**:
- `writeback_card_id`: Writeback card identifier
- `preferences`: User preferences object
- `rules`: Personal rules list (3-7 rules)
- `state_updates`: State map updates
- `trust_evidence`: Trust evidence list

#### Step 1.3: Update Personal Dataset Increment

After writeback card is completed, update personal dataset:
1. Add new preferences to dataset
2. Add new rules to dataset
3. Update state map
4. Add session artifacts to dataset
5. Update route templates (if applicable)

**Dataset Increment Content**:
- New preferences
- New rules
- Updated state map
- Session artifacts
- Route templates (if applicable)

**Output**:
- `dataset_increment_id`: Dataset increment identifier
- `updated_dataset`: Updated dataset object
- `increment_summary`: Summary of this week's increment

### Phase 2: Monthly Milestone Check

**Execution Order**:
1. Step 2.0: Check if milestone is due
2. Step 2.1: Generate milestone report
3. Step 2.2: Review progress and provide guidance

#### Step 2.0: Check if Milestone is Due

Check if monthly milestone is due:
- Calculate current month (1-12)
- Check if milestone report exists for current month
- If not, check if it's time to generate (first day of month)

**Output**:
- `milestone_due`: Boolean
- `current_month`: Current month number (1-12)
- `milestone_date`: Milestone date
- `next_milestone_date`: Next milestone date

#### Step 2.1: Generate Milestone Report

Generate monthly milestone report:
1. Aggregate all weekly sessions from past month
2. Calculate completion rate
3. Extract key learnings and patterns
4. Identify progress and gaps
5. Generate recommendations

**Milestone Report Content**:
- **Completion Status**: What user completed
- **Rules Learned**: What rules user now uses (3-7 rules)
- **Next Steps**: How user should proceed
- **Progress Metrics**: Completion rate, engagement rate, etc.

**Output**:
- `milestone_report_id`: Milestone report identifier
- `completion_status`: Completion status object
- `rules_learned`: Rules learned list
- `next_steps`: Next steps list
- `progress_metrics`: Progress metrics object

#### Step 2.2: Review Progress and Provide Guidance

Present milestone report to user:
1. Show completion status
2. Highlight rules learned
3. Provide next steps guidance
4. Address any concerns or gaps
5. Encourage continued participation

**Guidance Format**:
```
Monthly Milestone - [Track Name]
Month: [Month Number]

What You Completed:
- [Completion item 1]
- [Completion item 2]
...

Rules You Now Use:
1. [Rule 1]
2. [Rule 2]
...

How to Proceed:
- [Next step 1]
- [Next step 2]
...
```

**Acceptance Criteria**:
- ✅ Milestone report is clearly presented
- ✅ Completion status is accurate
- ✅ Rules learned are highlighted
- ✅ Next steps are actionable

### Phase 3: Final Personal Dataset Delivery

**Execution Order**:
1. Step 3.0: Check if track is completed
2. Step 3.1: Generate final Personal Dataset
3. Step 3.2: Export dataset in requested format
4. Step 3.3: Deliver dataset to user

#### Step 3.0: Check if Track is Completed

Check if user has completed 12 weeks:
- Calculate total weeks completed
- Check if all required sessions are completed
- Check if all writeback cards are completed
- Verify dataset is complete

**Output**:
- `track_completed`: Boolean
- `weeks_completed`: Total weeks completed (1-12)
- `completion_rate`: Completion rate percentage
- `dataset_complete`: Boolean

#### Step 3.1: Generate Final Personal Dataset

Generate final Personal Dataset after 12 weeks:
1. Collect all preferences from all sessions
2. Aggregate all rules (3-7 final rules)
3. Compile complete state map (at least 5 states)
4. Collect all route templates (if applicable)
5. Generate next phase action guide

**Personal Dataset Content** (minimum requirements):
- **State and Preference Map**: Complete state map with preferences
- **Choice Rules**: 3-7 personal choice rules
- **Practice Templates**: Practice or route templates (at least 1 if applicable)
- **Next Phase Action Guide**: Guidance for next phase

**Output**:
- `dataset_id`: Dataset identifier
- `dataset`: Personal Dataset object
- `dataset_completeness`: Dataset completeness check result

#### Step 3.2: Export Dataset in Requested Format

Export dataset in user's requested format:
- **JSON**: Structured JSON format
- **Markdown**: Human-readable Markdown format
- **Notion**: Notion database format

**Export Options**:
- Full dataset export
- Incremental export (only new data since last export)
- Custom format export

**Output**:
- `export_format`: Export format (json/markdown/notion)
- `export_file`: Exported file path or URL
- `export_timestamp`: Export timestamp

#### Step 3.3: Deliver Dataset to User

Deliver dataset to user:
1. Provide download link or file
2. Show dataset summary
3. Explain how to use the dataset
4. Provide next steps guidance

**Delivery Format**:
```
Personal Dataset - [Track Name]
Completion Date: [Date]

Your State and Preference Map:
[State map content]

Your Choice Rules:
1. [Rule 1]
2. [Rule 2]
...

Your Practice Templates:
[Template content]

Next Phase Action Guide:
[Action guide content]

Download: [Download link]
```

**Acceptance Criteria**:
- ✅ Dataset is complete (all required fields)
- ✅ Dataset contains at least 3 rules
- ✅ Dataset contains at least 5 states
- ✅ Dataset contains at least 1 route template (if applicable)
- ✅ Dataset is delivered in requested format

### Phase 4: Cohort Management

**Execution Order**:
1. Step 4.0: View cohort status
2. Step 4.1: Manage missed sessions
3. Step 4.2: Update subscription or cancel

#### Step 4.0: View Cohort Status

View current cohort status:
- Show cohort participants
- Show cohort schedule
- Show cohort progress
- Show upcoming sessions

**Output**:
- `cohort_status`: Cohort status object
- `participants`: Participant list
- `upcoming_sessions`: Upcoming sessions list
- `cohort_progress`: Cohort progress metrics

#### Step 4.1: Manage Missed Sessions

If user missed a session:
1. Identify missed session
2. Provide make-up options (if available)
3. Update progress tracking
4. Ensure writeback card can still be completed

**Make-up Options**:
- Attend next session early
- Complete session independently
- Watch session recording (if available)
- Schedule make-up session

**Output**:
- `missed_sessions`: Missed sessions list
- `makeup_options`: Make-up options list
- `progress_updated`: Boolean

#### Step 4.2: Update Subscription or Cancel

If user wants to update subscription:
1. Process payment (if required)
2. Update expiration date
3. Confirm renewal

If user wants to cancel:
1. Update subscription status to "cancelled"
2. Confirm cancellation
3. Inform user about access until expiration
4. Provide dataset export option (if applicable)

**Output**:
- `action_taken`: "renewed" | "cancelled" | "none"
- `new_expiration_date`: Updated expiration date (if renewed)

## Acceptance Criteria

### Subscription and Cohort Join
- ✅ User can subscribe to Annual Track
- ✅ Subscription is created with correct tier ("annual_track")
- ✅ User can join or create cohort
- ✅ Payment is processed (if required)
- ✅ Subscription expiration is set correctly (30 days or 365 days)

### Weekly Rhythm
- ✅ User can attend weekly sessions
- ✅ User can complete writeback cards
- ✅ User's dataset is updated each week
- ✅ Session artifacts are collected

### Monthly Milestone
- ✅ Monthly milestone report is generated
- ✅ Completion status is accurate
- ✅ Rules learned are highlighted
- ✅ Next steps are actionable

### Final Dataset Delivery
- ✅ Final Personal Dataset is generated after 12 weeks
- ✅ Dataset contains all required fields
- ✅ Dataset contains at least 3 rules
- ✅ Dataset contains at least 5 states
- ✅ Dataset is delivered in requested format

### Cohort Management
- ✅ User can view cohort status
- ✅ User can manage missed sessions
- ✅ User can update or cancel subscription

## Error Handling

### Subscription Errors
- If subscription creation fails: Inform user and retry
- If payment fails: Inform user and provide alternative payment methods
- If subscription expired: Prompt user to renew

### Session Errors
- If session is missed: Provide make-up options
- If session recording fails: Retry and inform user
- If session data is incomplete: Prompt user to complete

### Writeback Errors
- If writeback card is incomplete: Prompt user to complete
- If writeback generation fails: Retry and inform user

### Dataset Errors
- If dataset generation fails: Retry and inform user
- If dataset is incomplete: Check completeness and prompt user
- If export fails: Retry and inform user

## Notes

- Annual Track is a premium subscription ($29/month or $290/year)
- Focus is on being accompanied in living a worldview into life
- Weekly rhythm ensures consistent progress
- Monthly milestones provide checkpoints
- Final Personal Dataset is the key deliverable and renewal reason
- Completion rate target: ≥70%













