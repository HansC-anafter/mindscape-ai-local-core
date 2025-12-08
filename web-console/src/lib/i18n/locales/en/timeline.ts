/**
 * timeline i18n messages (English)
 */
import type { MessageKey } from '../../keys';

export const timelineEn = {

  // Timeline
  timeline: 'Timeline',
  timelineContentPlaceholder: 'Timeline content will be displayed here',
  viewFullTimeline: 'View Full Timeline',
  timelineUserMessage: 'User Message',
  timelineAssistantReply: 'Assistant Reply',
  timelineToolCall: 'Tool Call',
  timelineWorkspaceCreated: 'Workspace Created',

  // Timeline Panel Sections
  timelineRunning: 'Running',
  timelinePendingConfirmation: 'Pending Confirmation',
  timelineArchived: 'Archived',
  timelineHistory: 'History',
  noRunningExecutions: 'No running Playbooks',
  noPendingConfirmations: 'No steps pending confirmation',
  noArchivedExecutions: 'No archived executions',

  // Execution Console
  executionAISuggested: '(AI suggested, can still be changed during execution)',
  executionRequiresConfirmation: 'Requires Confirmation',
  executionSummary: 'Execution Summary',
  executionWaitingConfirmation: 'Waiting for Confirmation',
  executionConfirmationMessage: 'This step requires your confirmation to continue',
  executionConfirmContinue: 'Confirm and Continue',
  executionReject: 'Reject',
  executionFailed: 'Execution Failed',
  executionSelectStepForDetails: 'Select a step to view details',
  executionCancel: 'Cancel Execution',

} as const satisfies Partial<Record<MessageKey, string>>;
