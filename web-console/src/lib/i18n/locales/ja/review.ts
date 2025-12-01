/**
 * Review i18n messages (Japanese)
 * Review preferences and review-related functionality
 */
import type { MessageKey } from '../../keys';

export const reviewJa = {
  // Review Preferences
  reviewPreferences: '年間レビューリズム',
  reviewCadence: 'レビューリズム',
  reviewCadenceManual: '自動リマインダーなし',
  reviewCadenceWeekly: '週次',
  reviewCadenceMonthly: '月次',
  reviewCadenceDescription: 'システムがレビューをリマインドする頻度を選択',
  reviewDayOfWeek: '週の何曜日にリマインド',
  reviewDayOfMonth: '月の何日にリマインド',
  reviewTimeOfDay: 'リマインド時刻',
  reviewMinEntries: '最小記録数',
  reviewMinEntriesDescription: '少なくとも何件の記録が累積されたらリマインド（デフォルト：10）',
  reviewMinInsightEvents: '最小インサイトイベント数',
  reviewMinInsightEventsDescription: '少なくとも何回の「レビューする価値のあるコンテンツ」があったらリマインド（デフォルト：3）',
  dayOfWeekMonday: '月曜日',
  dayOfWeekTuesday: '火曜日',
  dayOfWeekWednesday: '水曜日',
  dayOfWeekThursday: '木曜日',
  dayOfWeekFriday: '金曜日',
  dayOfWeekSaturday: '土曜日',
  dayOfWeekSunday: '日曜日',

  // Review errors
  reviewStartFailed: 'レビューの開始に失敗しました：{error}',
} as const satisfies Partial<Record<MessageKey, string>>;

