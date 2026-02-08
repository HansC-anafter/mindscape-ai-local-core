---
playbook_code: yogacoach_course_scheduling
version: 1.0.0
locale: en
name: "Course Scheduling & Booking Management"
description: "Schedule sync, course create/edit/cancel, booking management, waitlist management, course change notifications"
capability_code: yogacoach
tags:
  - yoga
  - course
  - scheduling
---

# Playbook: Course Scheduling & Booking Management

**Playbook Code**: `yogacoach_course_scheduling`
**Version**: 1.0.0
**Purpose": Schedule sync, course create/edit/cancel, booking management, waitlist management, course change notifications

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `teacher_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "action": "book",
  "class_info": {
    "class_id": "class-abc123",
    "title": "Beginner Flow Yoga",
    "datetime": "2025-12-25T10:00:00Z",
    "duration_minutes": 60
  },
  "booking_info": {
    "user_id": "user-123"
  }
}
```

## Output Data

```json
{
  "class_info": {
    "class_id": "class-abc123",
    "status": "scheduled",
    "booking_url": "https://yogacoach.app/book/class-abc123",
    "students": [
      {
        "user_id": "user-123",
        "name": "John Doe",
        "booking_status": "confirmed"
      }
    ]
  },
  "booking_result": {
    "booking_id": "booking-xyz789",
    "status": "confirmed",
    "payment_url": "https://yogacoach.app/pay/abc12345",
    "confirmation_sent": true
  }
}
```

## Execution Steps

1. **Course Operations" (action: create_class/update_class/cancel_class)
   - Create/edit/cancel course
   - Sync to external scheduling system (Google Calendar/Calendly/MindBody)

2. **Booking Management" (action: book/cancel_booking)
   - Check course capacity
   - Create booking record
   - Generate payment link (if needed)

3. **Waitlist Management"
   - If course is full, add to waitlist
   - Auto-notify waitlist students when seats available

4. **Course Change Notifications"
   - Call C2 (Channel Delivery) to push course change notifications
   - Send Email notification (optional)

## Capability Dependencies

- `yogacoach.course_scheduler": Course scheduling
- `yogacoach.calendar_sync": Calendar sync
- `yogacoach.channel_delivery": Channel delivery (course change notifications)

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Error Handling

- Course full: Return error, add to waitlist
- Booking failed: Return error, log details
- Sync failed: Return error, log details

