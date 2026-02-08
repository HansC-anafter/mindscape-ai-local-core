---
playbook_code: event_addon_purchase
version: 1.0.0
capability_code: walkto_lab
name: Event Add-on Purchase
description: |
  Purchase add-on for a specific event to record your presence and create portable evidence.
  Purchase confirmation → Presence recording → Delivery.
  Note: This is a non-core add-on that does not affect the main co-learning track.
tags:
  - walkto
  - event
  - addon
  - purchase
  - optional

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
icon: 🎫
---

# Event Add-on Purchase - SOP

## Objective

Enable users to purchase add-on for a specific event to record their presence and create portable evidence. This is a **non-core add-on** that:

1. **Purchase Confirmation**: Confirm purchase eligibility and process payment
2. **Presence Recording**: Record user's presence at the event
3. **Evidence Creation**: Create portable evidence of attendance
4. **Delivery**: Deliver evidence to user

**Core Value**:
- Transform a single event attendance into portable evidence
- Create a record of your presence at a specific event
- Take away evidence that can be used independently

**Important Notes**:
- This is **NOT a purchasing service** (not buying products for users)
- This is a plugin to "transform an event attendance into portable evidence"
- This **never affects the main co-learning track**
- This is an optional add-on feature

## Execution Steps

### Phase 0: Preparation

**Execution Order**:
1. Step 0.0: Identify event
2. Step 0.1: Check purchase eligibility
3. Step 0.2: Confirm add-on details

#### Step 0.0: Identify Event

Get event information:
- `event_id`: Event identifier
- `event_name`: Event name
- `event_date`: Event date
- `event_location`: Event location
- `event_type`: Type of event

**Output**:
- `event_id`: Event identifier
- `event_info`: Event information object

#### Step 0.1: Check Purchase Eligibility

Check if user can purchase add-on:
- Verify user has active subscription (Lens Feed or Annual Track)
- Check if event is available for add-on purchase
- Verify event date is valid
- Check if user already purchased add-on for this event

**Eligibility Check**:
```
Purchase Eligibility Check:

Active Subscription: [Yes/No] ✅/❌
Event Available: [Yes/No] ✅/❌
Event Date Valid: [Yes/No] ✅/❌
Already Purchased: [Yes/No] ✅/❌

Eligible: [Yes/No]
```

**Output**:
- `eligible`: Boolean
- `eligibility_check`: Eligibility check results
- `subscription_status`: Subscription status

#### Step 0.2: Confirm Add-on Details

Present add-on details to user:
- What the add-on includes
- What evidence will be created
- Price and payment information
- Delivery format

**Add-on Details Format**:
```
Event Add-on Details:

Event: [Event Name]
Date: [Event Date]
Location: [Event Location]

Add-on Includes:
- Presence recording
- Evidence creation
- Portable evidence delivery

Price: [Price]
Payment: [Payment method]

Evidence Format: [Format]
```

**Output**:
- `addon_details`: Add-on details object
- `user_confirmed`: Boolean (user confirms purchase)

### Phase 1: Purchase Confirmation

**Execution Order**:
1. Step 1.0: Process payment
2. Step 1.1: Create purchase record
3. Step 1.2: Confirm purchase

#### Step 1.0: Process Payment

Process payment for add-on:
- Collect payment information
- Process payment transaction
- Verify payment success

**Payment Processing**:
```
Payment Processing:

Amount: [Amount]
Payment Method: [Method]
Transaction ID: [Transaction ID]

Status: [Processing/Success/Failed]
```

**Output**:
- `payment_processed`: Boolean
- `payment_status`: Payment status
- `transaction_id`: Transaction identifier

#### Step 1.1: Create Purchase Record

Create purchase record:
- Record purchase in database
- Link purchase to user and event
- Set purchase status

**Purchase Record Format**:
```
Purchase Record Created:

Purchase ID: [purchase_id]
User ID: [user_id]
Event ID: [event_id]
Purchase Date: [date]
Status: [active]
```

**Output**:
- `purchase_id`: Purchase identifier
- `purchase_record`: Purchase record object
- `purchase_status`: Purchase status

#### Step 1.2: Confirm Purchase

Confirm purchase to user:
- Show purchase confirmation
- Provide purchase details
- Explain next steps

**Purchase Confirmation Format**:
```
Purchase Confirmed:

Purchase ID: [purchase_id]
Event: [Event Name]
Date: [Event Date]
Amount: [Amount]

Next Steps:
1. Attend the event
2. Record your presence
3. Receive evidence
```

**Output**:
- `purchase_confirmed`: Boolean
- `confirmation_details`: Confirmation details object

### Phase 2: Presence Recording

**Execution Order**:
1. Step 2.0: Record event attendance
2. Step 2.1: Collect attendance evidence
3. Step 2.2: Verify presence

#### Step 2.0: Record Event Attendance

Record user's attendance at event:
- Get attendance confirmation from user
- Record attendance timestamp
- Collect basic attendance information

**Attendance Recording**:
```
Event Attendance Recorded:

Event: [Event Name]
Date: [Event Date]
Attendance Time: [timestamp]
User: [user_id]

Status: [attended]
```

**Output**:
- `attendance_recorded`: Boolean
- `attendance_timestamp`: Attendance timestamp
- `attendance_info`: Attendance information object

#### Step 2.1: Collect Attendance Evidence

Collect evidence of attendance:
- Photos from event (if provided)
- Notes or observations
- Artifacts from event
- Any other evidence user wants to include

**Evidence Collection**:
```
Evidence Collected:

Photos: [Count] photos
Notes: [Count] notes
Artifacts: [Count] artifacts
Other: [Other evidence]

Total Evidence Items: [Count]
```

**Output**:
- `evidence_collected`: Boolean
- `evidence_items`: Evidence items list
- `evidence_count`: Total evidence count

#### Step 2.2: Verify Presence

Verify user's presence:
- Cross-check attendance with event records (if available)
- Verify evidence authenticity
- Confirm presence is valid

**Presence Verification**:
```
Presence Verification:

Attendance Recorded: ✅
Evidence Collected: ✅
Verification: [Verified/Unverified]

Status: [Valid/Invalid]
```

**Output**:
- `presence_verified`: Boolean
- `verification_status`: Verification status
- `verification_details`: Verification details

### Phase 3: Evidence Creation

**Execution Order**:
1. Step 3.0: Compile evidence
2. Step 3.1: Format evidence
3. Step 3.2: Create portable evidence

#### Step 3.0: Compile Evidence

Compile all evidence into a single package:
- Organize photos, notes, artifacts
- Create evidence summary
- Structure evidence package

**Evidence Compilation**:
```
Evidence Compiled:

Event: [Event Name]
Date: [Event Date]
User: [user_id]

Evidence Package:
- Photos: [Count]
- Notes: [Count]
- Artifacts: [Count]
- Summary: [Summary text]

Total Items: [Count]
```

**Output**:
- `evidence_compiled`: Boolean
- `evidence_package`: Evidence package object
- `package_summary`: Package summary

#### Step 3.1: Format Evidence

Format evidence according to delivery format:
- Format as requested (PDF/Markdown/Notion/etc.)
- Include metadata and timestamps
- Ensure portability

**Evidence Formatting**:
```
Evidence Formatted:

Format: [Format]
Structure: [Structure]
Metadata: [Metadata included]

Ready for Delivery: [Yes/No]
```

**Output**:
- `evidence_formatted`: Boolean
- `formatted_evidence`: Formatted evidence object
- `format_type`: Format type

#### Step 3.2: Create Portable Evidence

Create final portable evidence:
- Generate evidence file
- Include all components
- Ensure evidence is complete

**Portable Evidence Format**:
```
Portable Evidence Created:

File: [file_name]
Format: [format]
Size: [size]
Components:
- Attendance record
- Photos
- Notes
- Artifacts
- Summary

Status: [Complete]
```

**Output**:
- `portable_evidence`: Portable evidence object
- `evidence_file`: Evidence file path or URL
- `evidence_complete`: Boolean

### Phase 4: Delivery

**Execution Order**:
1. Step 4.0: Present evidence summary
2. Step 4.1: Provide download
3. Step 4.2: Confirm delivery

#### Step 4.0: Present Evidence Summary

Present evidence summary to user:
- Show evidence components
- Display key information
- Highlight evidence value

**Evidence Summary Format**:
```
Event Add-on Evidence Summary

Event: [Event Name]
Date: [Event Date]
Purchase ID: [purchase_id]

Evidence Components:
- Attendance Record: [Included]
- Photos: [Count] photos
- Notes: [Count] notes
- Artifacts: [Count] artifacts
- Summary: [Included]

Format: [format]
File Size: [size]
```

**Output**:
- `summary_presented`: Boolean
- `evidence_summary`: Evidence summary object

#### Step 4.1: Provide Download

Provide download link or file:
- Share download link
- Or provide direct file download
- Include instructions

**Download Format**:
```
Download Your Evidence:

[Download Link] or [Download Button]

File: event_evidence_[event_id]_[user_id]_[timestamp].[ext]
Format: [format]
Size: [size]

Valid for: [duration]
```

**Output**:
- `download_provided`: Boolean
- `download_link`: Download link
- `download_instructions`: Download instructions

#### Step 4.2: Confirm Delivery

Confirm evidence delivery:
- Verify user received evidence
- Confirm evidence is accessible
- Provide support if needed

**Delivery Confirmation**:
```
Evidence Delivered:

Delivery Date: [date]
Delivery Status: [Delivered]
Access: [Accessible]

Support: [Available if needed]
```

**Output**:
- `delivery_confirmed`: Boolean
- `delivery_status`: Delivery status
- `delivery_metadata`: Delivery metadata object

## Acceptance Criteria

### Purchase Confirmation
- ✅ User is eligible to purchase add-on
- ✅ Payment is processed successfully
- ✅ Purchase record is created
- ✅ Purchase is confirmed

### Presence Recording
- ✅ Event attendance is recorded
- ✅ Attendance evidence is collected
- ✅ Presence is verified

### Evidence Creation
- ✅ Evidence is compiled
- ✅ Evidence is formatted
- ✅ Portable evidence is created

### Delivery
- ✅ Evidence summary is presented
- ✅ Download is provided
- ✅ Delivery is confirmed

## Error Handling

### Preparation Errors
- If event not found: Inform user and provide alternatives
- If user not eligible: Explain eligibility requirements
- If event not available: Inform user and suggest alternatives

### Purchase Errors
- If payment fails: Retry payment or provide alternative payment methods
- If purchase record creation fails: Retry and inform user
- If purchase confirmation fails: Verify purchase and retry

### Presence Recording Errors
- If attendance cannot be recorded: Prompt user to provide information
- If evidence collection fails: Retry collection or allow manual upload
- If presence verification fails: Review evidence and retry

### Evidence Creation Errors
- If evidence compilation fails: Retry compilation
- If formatting fails: Fix format issues and retry
- If portable evidence creation fails: Retry creation

### Delivery Errors
- If download link fails: Regenerate link
- If file not accessible: Check permissions and retry
- If delivery confirmation fails: Verify delivery and retry

## Notes

- Event Add-on is a **non-core optional feature**
- This is **NOT a purchasing service** (not buying products)
- This is a plugin to "transform event attendance into portable evidence"
- This **never affects the main co-learning track**
- Evidence is portable and can be used independently
- Add-on requires active subscription (Lens Feed or Annual Track)













