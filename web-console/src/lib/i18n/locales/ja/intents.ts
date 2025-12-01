/**
 * Intents i18n messages (Japanese)
 * Intent cards and long-term goals
 */
import type { MessageKey } from '../../keys';

export const intentsJa = {
  // Intents
  intents: '意図カード',
  intentsDescription: '長期目標とプロジェクトを追跡',
  intentTitle: 'タイトル',
  intentDescription: '説明',
  intentStatus: 'ステータス',
  intentPriority: '優先度',
  intentProgress: '進捗',
  intentTags: 'タグ',
  intentCategory: 'カテゴリ',
  intentDueDate: '期限',
  newIntent: '新しい意図カード',
  editIntent: '意図カードを編集',
} as const satisfies Partial<Record<MessageKey, string>>;

