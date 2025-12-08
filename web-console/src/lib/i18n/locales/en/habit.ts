/**
 * habit i18n messages (English)
 */
import type { MessageKey } from '../../keys';

export const habitEn = {

  // Habit Learning
  habitSuggestions: 'Habit Suggestions',
  enableHabitSuggestions: 'Enable Habit Suggestions',
  enableHabitSuggestionsDescription: 'The system will propose habit candidates based on your usage records, which require your confirmation before becoming defaults',
  habitSuggestionsDisabled: 'Habit suggestions feature is disabled',
  habitSuggestionsEnabled: 'Habit suggestions feature is enabled',
  habitDetected: 'Detected frequent use of',
  habitSuggestionMessage: 'Detected frequent use of "{value}" as {key}. In the last {count} uses, this preference appeared {confidence}% of the time. Set as default?',
  confirmHabit: 'Set as Default',
  rejectHabit: 'Later',
  habitConfirmSuccess: 'Habit set as default',
  habitRejectSuccess: 'Noted, will remind later',
  habitManagement: 'Habit Management',
  habitCandidates: 'Habit Candidates',
  habitAuditLogs: 'Audit Logs',
  habitMetrics: 'Statistics',
  noPendingCandidates: 'No pending habit candidates',
  totalObservations: 'Total Observations',
  totalCandidates: 'Total Candidates',
  pendingCandidates: 'Pending',
  confirmedCandidates: 'Confirmed',
  rejectedCandidates: 'Rejected',
  acceptanceRate: 'Acceptance Rate',
  candidateHitRate: 'Candidate Hit Rate',
  habitKey: 'Habit Type',
  habitValue: 'Habit Value',
  habitConfidence: 'Confidence',
  habitEvidenceCount: 'Evidence Count',
  habitStatus: 'Status',
  habitPending: 'Pending',
  habitConfirmed: 'Confirmed',
  habitRejected: 'Rejected',
  habitSuperseded: 'Superseded',
  habitFirstSeenAt: 'First Seen',
  habitLastSeenAt: 'Last Seen',
  habitRollback: 'Rollback',
  habitViewDetails: 'View Details',
  habitViewAuditLogs: 'View Audit Logs',

  // Habit errors
  habitConfirmFailed: 'Confirm failed: {error}',
  habitRejectFailed: 'Reject failed: {error}',

} as const satisfies Partial<Record<MessageKey, string>>;
