/**
 * habit i18n messages (Traditional Chinese)
 */
import type { MessageKey } from '../../keys';

export const habitZhTW = {

  // Habit Learning
  habitSuggestions: '習慣建議',
  enableHabitSuggestions: '啟用習慣建議',
  enableHabitSuggestionsDescription: '系統會基於你的使用記錄提出習慣候選，需你確認後才會成為預設',
  habitSuggestionsDisabled: '習慣建議功能已關閉',
  habitSuggestionsEnabled: '習慣建議功能已啟用',
  habitDetected: '偵測到你常用',
  habitSuggestionMessage: '偵測到你常用「{value}」作為 {key}。在最近 {count} 次使用中，這個偏好出現了 {confidence}% 的機率。要設為預設嗎？',
  confirmHabit: '設為預設',
  rejectHabit: '稍後再說',
  habitConfirmSuccess: '習慣已設為預設',
  habitRejectSuccess: '已記錄，稍後再提醒',
  habitManagement: '習慣管理',
  habitCandidates: '候選習慣',
  habitAuditLogs: '審計記錄',
  habitMetrics: '統計資訊',
  noPendingCandidates: '目前沒有待確認的習慣候選',
  totalObservations: '觀察記錄總數',
  totalCandidates: '候選總數',
  pendingCandidates: '待確認',
  confirmedCandidates: '已確認',
  rejectedCandidates: '已拒絕',
  acceptanceRate: '接受率',
  candidateHitRate: '候選命中率',
  habitKey: '習慣類型',
  habitValue: '習慣值',
  habitConfidence: '信心度',
  habitEvidenceCount: '證據次數',
  habitStatus: '狀態',
  habitPending: '待確認',
  habitConfirmed: '已確認',
  habitRejected: '已拒絕',
  habitSuperseded: '已取代',
  habitFirstSeenAt: '首次觀察',
  habitLastSeenAt: '最後觀察',
  habitRollback: '回滾',
  habitViewDetails: '查看詳情',
  habitViewAuditLogs: '查看審計記錄',

  // Habit errors
  habitConfirmFailed: '確認失敗：{error}',
  habitRejectFailed: '拒絕失敗：{error}',

} as const satisfies Partial<Record<MessageKey, string>>;
