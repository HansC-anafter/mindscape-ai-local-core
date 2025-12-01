/**
 * Timeline i18n messages
 * Timeline and event display
 */
import type { MessageKey } from '../keys';

export const timelineZhTW = {
  // Timeline
  timeline: 'Timeline',
  timelineContentPlaceholder: 'Timeline content will be displayed here',
  viewFullTimeline: 'View Full Timeline',
  timelineUserMessage: '用户消息',
  timelineAssistantReply: '助手回复',
  timelineToolCall: '工具调用',
  timelineWorkspaceCreated: '工作区创建',

  // Timeline Panel Sections
  timelineRunning: '執行中',
  timelinePendingConfirmation: '待確認',
  timelineArchived: '已存檔',
  timelineHistory: '歷史記錄',
  noRunningExecutions: '目前沒有執行中的 Playbook',
  noPendingConfirmations: '目前沒有待確認的步驟',
  noArchivedExecutions: '目前沒有已存檔的執行',

  // Execution Console
  executionAISuggested: '(AI 推測，執行中仍可更改)',
  executionRequiresConfirmation: '需要確認',
  executionSummary: '執行摘要',
  executionWaitingConfirmation: '等待確認',
  executionConfirmationMessage: '此步驟需要您的確認才能繼續執行',
  executionConfirmContinue: '確認並繼續',
  executionReject: '拒絕',
  executionFailed: '執行失敗',
  executionSelectStepForDetails: '選擇步驟查看詳情',
  executionCancel: '取消執行',
} as const satisfies Partial<Record<MessageKey, string>>;

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
