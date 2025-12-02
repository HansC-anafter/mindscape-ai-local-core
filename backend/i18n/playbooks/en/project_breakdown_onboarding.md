---
playbook_code: project_breakdown_onboarding
version: 1.0.0
locale: en
name: First Long-term Task (Cold Start Version)
description: "Cold start specific: Help new users quickly break down the first project they want to work on"
tags:
  - onboarding
  - planning
  - project
  - cold-start

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
onboarding_task: task2
icon: 📋
required_tools: []
scope:
  visibility: system
  editable: false
owner:
  type: system
---

# First Long-term Task - Cold Start SOP

## Goal
Help new users quickly break down "the one thing they most want to accomplish" into actionable steps, and automatically create the first long-term task card.

## Personalization

### Use User's Opening Role Card
Based on content filled in Task 1:
- **Currently doing**: {self_description.identity}
- **Want to accomplish**: {self_description.solving}
- **Thinking about**: {self_description.thinking}

Use this information to understand user's background and needs, adjust suggestion angle.

## Execution Steps

### Opening
```
I see you want to accomplish "{self_description.solving}". Let me help you break it down into actionable steps.

This won't take long, about 3-5 minutes to complete 🚀
```

### Step 1: Understand Project Core (2 Questions)

**Question 1: Tell me more about this**
```
First, tell me what "{self_description.solving}" specifically is?

You can describe it freely, I'll help organize the key points.
```

**Question 2: What state do you hope to achieve?**
```
If this is accomplished, what results do you expect to see?
(No need to be formal, just say what you're thinking)
```

### Step 2: Quick Breakdown (AI Proactively Suggests)

Based on user's description, **AI proactively suggests 3-4 key steps**:

```
Good! I've organized a few key steps for you:

1. [Step 1 Name]
   - What specifically needs to be done
   - Why this is the first step

2. [Step 2 Name]
   - What specifically needs to be done
   - Depends on what from Step 1

3. [Step 3 Name]
   - What specifically needs to be done
   - This step completes it

4. (Optional) [Step 4 Name]
   - If needed...

Does this breakdown work? Any adjustments?
```

**User Feedback Handling:**
- If says "OK" → Proceed to Step 3
- If has adjustment needs → Modify and confirm again

### Step 3: Identify Next Action

```
Great! Which step can you start on fastest?

I'll mark it as "next action", and you can start directly from here later.
```

### Step 4: Completion Summary and Create Task Card

```
✅ Done organizing!

I've created your first "Long-term Task Card":

📋 Project: {project_title}
Goal: {project_goal}

Key Steps:
1. ✓ {step1}
2. → {step2} (Next)
3. {step3}
4. {step4}

This task card will continuously track your progress, and I'll automatically update status from your work records later.

---

💡 Your Mindscape task progress: 2/3 complete
Just one more task "This Week's Work Rhythm" to fully activate!
```

## Output Format (Machine Readable)

After conversation ends, output JSON format for system processing:

```json
{
  "onboarding_task": "task2",
  "project_data": {
    "title": "Project Title",
    "description": "Project Description",
    "goal": "Expected State",
    "steps": [
      {
        "order": 1,
        "title": "Step 1",
        "description": "What specifically needs to be done",
        "status": "pending"
      },
      {
        "order": 2,
        "title": "Step 2",
        "description": "What specifically needs to be done",
        "status": "next",
        "is_next_action": true
      }
    ],
    "next_action": "Step 2",
    "estimated_duration": "2-3 weeks"
  },
  "extracted_insights": {
    "user_working_style": "Prefers quick action / Likes framework first",
    "potential_blockers": ["Not enough time", "Uncertain about technical approach"],
    "confidence_level": "Medium confidence"
  }
}
```

## Integration with Mindscape

1. **Automatically Create Intent Card**
   - Use `project_data` to create an `IntentCard`
   - Set as `status: active`, `priority: high`
   - Mark as onboarding task source

2. **Update Cold Start Status**
   - Call `/api/v1/mindscape/onboarding/complete-task2`
   - Pass `execution_id` and created `intent_id`

3. **Extract Seeds**
   - Extract work style seeds from `extracted_insights`
   - Write to `mindscape_seed_log`

## Tone and Style

- ✅ Casual, conversational ("搞定" instead of "完成")
- ✅ Proactive suggestions, don't make users fill blanks
- ✅ Quick completion (3-5 minutes), don't ask too many details
- ✅ Clear progress indication (2/3 complete)

## Success Criteria

- User clearly knows 3-4 key steps for this project
- User knows what to do next
- First long-term task card automatically created
- Cold start progress updated to 2/3
