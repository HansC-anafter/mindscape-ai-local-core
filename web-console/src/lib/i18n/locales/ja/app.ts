/**
 * App-level i18n messages (Japanese)
 * Application name, subtitle, core concepts
 */
import type { MessageKey } from '../../keys';

export const appJa = {
  // App
  appName: 'Mindscape AI',
  appSubtitle: '個人 AI チームコンソール',
  appWorkstation: 'Mindscape AI ワークステーション',
  appCoreConcept: 'マインドスケープ：あなたの個人的なコンテキストを保存 | プレイブック：「再利用する価値がある」ワークフローを保存',
} as const satisfies Partial<Record<MessageKey, string>>;

