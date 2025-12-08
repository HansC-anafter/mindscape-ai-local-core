/**
 * Intents i18n messages
 * Intent cards and long-term goals
 */
import type { MessageKey } from '../keys';

export const intentsZhTW = {
  // Intents
  intents: '意圖卡',
  intentsDescription: '追蹤你的長線目標與專案',
  intentTitle: '標題',
  intentDescription: '描述',
  intentStatus: '狀態',
  intentPriority: '優先級',
  intentProgress: '進度',
  intentTags: '標籤',
  intentCategory: '分類',
  intentDueDate: '到期日',
  newIntent: '新增意圖卡',
  editIntent: '編輯意圖卡',
} as const satisfies Partial<Record<MessageKey, string>>;

export const intentsEn = {
  // Intents
  intents: 'Intent Cards',
  intentsDescription: 'Track your long-term goals and projects',
  intentTitle: 'Title',
  intentDescription: 'Description',
  intentStatus: 'Status',
  intentPriority: 'Priority',
  intentProgress: 'Progress',
  intentTags: 'Tags',
  intentCategory: 'Category',
  intentDueDate: 'Due Date',
  newIntent: 'New Intent Card',
  editIntent: 'Edit Intent Card',
} as const satisfies Partial<Record<MessageKey, string>>;
