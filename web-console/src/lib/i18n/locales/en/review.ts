/**
 * review i18n messages (English)
 */
import type { MessageKey } from '../../keys';

export const reviewEn = {

  // Review Preferences
  reviewPreferences: 'Annual Review Rhythm',
  reviewCadence: 'Review Cadence',
  reviewCadenceManual: 'No automatic reminders',
  reviewCadenceWeekly: 'Weekly',
  reviewCadenceMonthly: 'Monthly',
  reviewCadenceDescription: 'Choose how often the system reminds you to review',
  reviewDayOfWeek: 'Day of week',
  reviewDayOfMonth: 'Day of month',
  reviewTimeOfDay: 'Reminder time',
  reviewMinEntries: 'Minimum entries',
  reviewMinEntriesDescription: 'Minimum number of entries before reminder (default: 10)',
  reviewMinInsightEvents: 'Minimum insight events',
  reviewMinInsightEventsDescription: 'Minimum number of "worth reviewing" events before reminder (default: 3)',
  dayOfWeekMonday: 'Monday',
  dayOfWeekTuesday: 'Tuesday',
  dayOfWeekWednesday: 'Wednesday',
  dayOfWeekThursday: 'Thursday',
  dayOfWeekFriday: 'Friday',
  dayOfWeekSaturday: 'Saturday',
  dayOfWeekSunday: 'Sunday',

  // Review errors
  reviewStartFailed: 'Failed to start review: {error}',

} as const satisfies Partial<Record<MessageKey, string>>;
