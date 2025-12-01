/**
 * Habit Learning i18n messages (Japanese)
 * Habit suggestions and habit management
 */
import type { MessageKey } from '../../keys';

export const habitJa = {
  // Habit Learning
  habitSuggestions: '習慣提案',
  enableHabitSuggestions: '習慣提案を有効化',
  enableHabitSuggestionsDescription: 'システムは使用記録に基づいて習慣候補を提案します。確認後にデフォルトになります',
  habitSuggestionsDisabled: '習慣提案機能は無効です',
  habitSuggestionsEnabled: '習慣提案機能は有効です',
  habitDetected: '頻繁に使用されていることを検出',
  habitSuggestionMessage: '「{value}」を {key} として頻繁に使用していることを検出しました。最近 {count} 回の使用で、この好みは {confidence}% の確率で出現しました。デフォルトに設定しますか？',
  confirmHabit: 'デフォルトに設定',
  rejectHabit: '後で',
  habitConfirmSuccess: '習慣がデフォルトに設定されました',
  habitRejectSuccess: '記録しました。後でリマインドします',
  habitManagement: '習慣管理',
  habitCandidates: '習慣候補',
  habitAuditLogs: '監査ログ',
  habitMetrics: '統計情報',
  noPendingCandidates: '現在保留中の習慣候補はありません',
  totalObservations: '観察記録の総数',
  totalCandidates: '候補の総数',
  pendingCandidates: '保留中',
  confirmedCandidates: '確認済み',
  rejectedCandidates: '拒否済み',
  acceptanceRate: '受入率',
  candidateHitRate: '候補命中率',
  habitKey: '習慣タイプ',
  habitValue: '習慣値',
  habitConfidence: '信頼度',
  habitEvidenceCount: '証拠回数',
  habitStatus: 'ステータス',
  habitPending: '保留中',
  habitConfirmed: '確認済み',
  habitRejected: '拒否済み',
  habitSuperseded: '置き換え済み',
  habitFirstSeenAt: '初回観察',
  habitLastSeenAt: '最終観察',
  habitRollback: 'ロールバック',
  habitViewDetails: '詳細を表示',
  habitViewAuditLogs: '監査ログを表示',

  // Habit errors
  habitConfirmFailed: '確認に失敗しました：{error}',
  habitRejectFailed: '拒否に失敗しました：{error}',
} as const satisfies Partial<Record<MessageKey, string>>;

