/**
 * Timeline i18n messages (Japanese)
 * Timeline and event display
 */
import type { MessageKey } from '../../keys';

export const timelineJa = {
  // Timeline
  timeline: 'タイムライン',
  timelineContentPlaceholder: 'タイムラインコンテンツがここに表示されます',
  viewFullTimeline: '完全なタイムラインを表示',
  timelineUserMessage: 'ユーザーメッセージ',
  timelineAssistantReply: 'アシスタントの返信',
  timelineToolCall: 'ツール呼び出し',
  timelineWorkspaceCreated: 'ワークスペース作成',

  // Timeline Panel Sections
  timelineRunning: '実行中',
  timelinePendingConfirmation: '確認待ち',
  timelineArchived: 'アーカイブ済み',
  timelineHistory: '履歴',
  noRunningExecutions: '実行中のプレイブックはありません',
  noPendingConfirmations: '確認待ちのステップはありません',
  noArchivedExecutions: 'アーカイブ済みの実行はありません',

  // Execution Console
  executionAISuggested: '（AI 推測、実行中でも変更可能）',
  executionRequiresConfirmation: '確認が必要',
  executionSummary: '実行サマリー',
  executionWaitingConfirmation: '確認待ち',
  executionConfirmationMessage: 'このステップを続行するには確認が必要です',
  executionConfirmContinue: '確認して続行',
  executionReject: '拒否',
  executionFailed: '実行失敗',
  executionSelectStepForDetails: '詳細を表示するステップを選択',
  executionCancel: '実行をキャンセル',
} as const satisfies Partial<Record<MessageKey, string>>;

