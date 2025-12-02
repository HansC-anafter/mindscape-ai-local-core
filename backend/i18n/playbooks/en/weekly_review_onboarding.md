---
playbook_code: weekly_review_onboarding
version: 1.0.0
locale: en
name: This Week's Work Rhythm (Cold Start Version)
description: "Cold start specific: Quickly understand user's work habits and rhythm"
tags:
  - onboarding
  - planning
  - work-rhythm
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
onboarding_task: task3
icon: ⏰
required_tools: []
scope:
  visibility: system
  editable: false
owner:
  type: system
---

# This Week's Work Rhythm - Cold Start SOP

## Goal
Quickly understand user's work habits, commonly used tools, time rhythm, and automatically extract work pattern seeds to complete cold start process.

## Personalization

### Use User's Opening Role Card
Based on content filled in Task 1:
- **Currently doing**: {self_description.identity}
- **Want to accomplish**: {self_description.solving}

Use this information to adjust question angles and examples.

## Execution Steps

### Opening
```
Last warm-up task! 🎯

Want to understand your work habits better, so I can plan tasks that match your rhythm later.

Just 3 questions, won't take long 😊
```

### Question 1: Things to Do This Week

**Question Format**
```
What 3 things are you planning to do this week?
(Projects, tasks, meetings, personal goals all count, just say what you have in mind)
```

**Follow-up (Optional)**
If user answers very briefly, can follow up:
```
Good, of these 3 things, which one do you think is most important / want to tackle first?
```

**Information to Extract:**
- Task types (technical development / content creation / meetings / learning...)
- Priority judgment patterns
- Task granularity (large projects vs small tasks)

### Question 2: Commonly Used Tools

**Question Format**
```
What tools do you usually use for work?

For example:
• WordPress / Notion / Google Docs (writing / notes)
• GitHub / GitLab (code)
• Figma / Sketch (design)
• Other tools you commonly use...

Just mention a few 👍
```

**Information to Extract:**
- Tool categories (CMS / notes / code / design / project management)
- Tool combinations (judge workflow)
- Cloud vs local preferences

### Question 3: Work Rhythm Preferences

**Question Format (Multiple Choice + Free Answer)**
```
What kind of work rhythm do you prefer?

You can choose one, or directly say your habit:

A. Focus on important tasks in the morning
B. More inspiration at night, suitable for deep work
C. Prefer focusing on one thing at a time, finish before switching
D. Prefer multitasking, advancing multiple tasks simultaneously
E. Other: (your own answer)

Or do you have other work rhythm preferences?
```

**Follow-up (If user chose A or B)**
```
What time do you usually start work / when do you feel most productive?
```

**Information to Extract:**
- Time preferences (morning person / night owl)
- Task processing mode (focused / multitasking)
- Work hours (what time to what time)

### Step 4: Completion Summary

```
Good! I've noted it down 📝

Your work rhythm:
• This week's focus: {weekly_tasks}
• Common tools: {tools}
• Preferred time: {time_preference}
• Task mode: {work_mode}

I'll match your habits when planning tasks later 👍

---

🎉 Mindscape is fully activated!

You've completed all warm-up tasks:
✅ Task 1: Opening Role Card
✅ Task 2: First Long-term Task
✅ Task 3: This Week's Work Rhythm

From now on, every time you complete a task, the system will extract new clues from usage records,
and ask if you want to "upgrade" this mindscape.

[ Return to Mindscape ]  [ Start a Task Directly ]
```

## Output Format (Machine Readable)

After conversation ends, output JSON format for system processing:

```json
{
  "onboarding_task": "task3",
  "work_rhythm_data": {
    "weekly_tasks": [
      {
        "task": "Task 1",
        "type": "development",
        "priority": "high",
        "estimated_hours": 10
      }
    ],
    "tools": [
      {
        "name": "WordPress",
        "category": "cms",
        "usage_frequency": "daily"
      },
      {
        "name": "Notion",
        "category": "notes",
        "usage_frequency": "daily"
      }
    ],
    "time_preferences": {
      "preferred_time": "morning",
      "work_start": "09:00",
      "peak_hours": "09:00-12:00",
      "focus_duration": "2-3 hours"
    },
    "work_mode": {
      "style": "focused",
      "multitasking": false,
      "break_frequency": "every_2_hours",
      "context_switching_tolerance": "low"
    }
  },
  "extracted_seeds": [
    {
      "seed_type": "preference",
      "seed_text": "Prefers focusing on important tasks in the morning",
      "confidence": 0.8
    },
    {
      "seed_type": "preference",
      "seed_text": "Likes focusing on one thing at a time, finish before switching",
      "confidence": 0.9
    },
    {
      "seed_type": "entity",
      "seed_text": "WordPress",
      "metadata": {
        "category": "tool",
        "usage": "daily"
      },
      "confidence": 1.0
    },
    {
      "seed_type": "entity",
      "seed_text": "Notion",
      "metadata": {
        "category": "tool",
        "usage": "daily"
      },
      "confidence": 1.0
    }
  ]
}
```

## Integration with Mindscape

1. **Create Work Pattern Seeds**
   - Use `extracted_seeds` to write to `mindscape_seed_log`
   - Mark source as `onboarding_task3`

2. **Update Cold Start Status**
   - Call `/api/v1/mindscape/onboarding/complete-task3`
   - Pass `execution_id` and `created_seeds_count`

3. **Trigger Congratulations Message**
   - Frontend detects 3/3 completion
   - Display congratulations banner

## Tone and Style

- ✅ Casual, like chatting with a friend ("聊 3 個問題")
- ✅ Provide options to reduce thinking burden
- ✅ Quick completion (3-5 minutes)
- ✅ Clear celebration of completion (🎉 + confetti)

## Success Criteria

- AI understands user's work time preferences
- AI knows user's commonly used tools
- AI knows user's task processing mode (focused vs multitasking)
- Automatically created 4-6 work pattern seeds
- Cold start progress updated to 3/3 (complete)
- Congratulations message triggered
