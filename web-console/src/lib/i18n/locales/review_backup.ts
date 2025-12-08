/**
 * Review i18n messages
 * Review preferences and review-related functionality
 */
import type { MessageKey } from '../keys';

export const reviewZhTW = {
  // Review Preferences
  reviewPreferences: '年度回顧節奏',
  reviewCadence: '回顧節奏',
  reviewCadenceManual: '不自動提醒',
  reviewCadenceWeekly: '每週',
  reviewCadenceMonthly: '每月',
  reviewCadenceDescription: '選擇系統提醒你進行回顧的頻率',
  reviewDayOfWeek: '每週幾提醒',
  reviewDayOfMonth: '每月幾號提醒',
  reviewTimeOfDay: '提醒時間',
  reviewMinEntries: '最少記錄數',
  reviewMinEntriesDescription: '至少累積幾條記錄才提醒（預設：10）',
  reviewMinInsightEvents: '最少 Insight 事件數',
  reviewMinInsightEventsDescription: '至少有幾次「值得回顧的內容」才提醒（預設：3）',
  dayOfWeekMonday: '星期一',
  dayOfWeekTuesday: '星期二',
  dayOfWeekWednesday: '星期三',
  dayOfWeekThursday: '星期四',
  dayOfWeekFriday: '星期五',
  dayOfWeekSaturday: '星期六',
  dayOfWeekSunday: '星期日',

  // Review errors
  reviewStartFailed: '開始回顧失敗：{error}',
} as const satisfies Partial<Record<MessageKey, string>>;

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
