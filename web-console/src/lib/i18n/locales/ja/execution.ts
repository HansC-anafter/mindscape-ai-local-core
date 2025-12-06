/**
 * Execution i18n messages (Japanese)
 * Playbook execution, workspace execution inspector, and related UI
 */
import type { MessageKey } from '../../keys';

export const executionJa = {
  // Playbook Execution Inspector
  runInsightDraftChanges: '実行インサイトとドラフト変更',
  reviewAISuggestions: 'AI の提案を確認し、変更を適用してこのプレイブックを改善する',
  aiAnalysis: 'AI 分析',
  apply: '適用',
  discard: '破棄',
  step: 'ステップ',
  noRevisionSuggestions: '修正提案はまだありません。',
  chatWithPlaybookInspector: 'プレイブックインスペクターとチャットして提案を取得する。',
  revisionDraft: '修正ドラフト',
  aiSuggestedChangesWillAppear: 'AI が提案した変更がここに表示されます',
  stepsTimeline: 'ステップタイムライン',
  eventStream: 'イベントストリーム',
  noEventsYet: 'イベントはまだありません',
  toolCalls: 'ツール呼び出し',
  selectStepToViewDetails: '詳細を表示するステップを選択',
  editPlaybook: 'プレイブックを編集',

  // Execution Status
  executionStatusRunning: '実行中',
  executionStatusSucceeded: '成功',
  executionStatusFailed: '失敗',
  executionStatusPaused: '一時停止',
  executionStatusUnknown: '不明',

  // Trigger Source
  triggerSourceAuto: '自動',
  triggerSourceSuggested: '提案',
  triggerSourceManual: '手動',
  triggerSourceUnknown: '不明',

  // Actions
  stop: '停止',
  stopping: '停止中...',
  reload: '再読み込み',
  reloading: '再読み込み中...',
  restart: 'リセット',
  restarting: 'リセット中...',
  reloadPlaybook: 'プレイブックを再読み込み',
  restartExecution: '実行をリセット',
  confirmRestartExecution: 'この実行をリセットしてもよろしいですか？\n\n最初から新しい実行が作成され、現在の実行がキャンセルされます。',
  restartingExecution: '実行をリセット中です。しばらくお待ちください...',
  executionRestarted: '実行がリセットされました',
  executionRestartFailed: '実行のリセットに失敗しました',
  view: '表示',

  // Execution Header
  runNumber: '実行 #{number}',
  stepProgress: 'ステップ {current} / {total}',
  startedAt: '開始時刻 {time}',
  byUser: 'ユーザー: {user}',
  unknownUser: '不明なユーザー',
  unknownPlaybook: '不明なプレイブック',
  errorLabel: 'エラー：',

  // Step Details
  noEvents: 'イベントはまだありません',
  agent: 'エージェント：',
  tool: 'ツール：',
  collaboration: 'コラボレーション：',
  startingPlaybookExecution: 'プレイブック実行を開始: {playbook}',
  stepNumber: 'ステップ {number}',
  unnamed: '名前なし',
  tools: 'ツール',
  pending: '待機中',

  // Execution Messages
  thisExecutionFailed: 'この実行は失敗しました: {reason}。問題を特定するためにステップタイムラインを確認してください。',

  // Playbook Inspector
  playbookInspector: 'プレイブックインスペクター',
  playbookRun: 'プレイブック - 実行 #{number}',
  askPlaybookInspector: 'この実行についてプレイブックインスペクターに尋ねてください。ステップ、イベント、エラーを知っています。',
  explainWhyFailed: 'この実行が失敗した理由を説明する',
  suggestNextSteps: '次のステップを提案する',
  reviewPlaybookSteps: 'プレイブックステップを確認する',
  explainWhyFailedPrompt: 'この実行が失敗した理由を説明できますか？何が問題で、どう修正すればよいですか？',
  explainWhyFailedPromptAlt: 'この実行の現在のステータスは何ですか？',
  suggestNextStepsPrompt: 'この問題を解決するか、実行を続行するために次に何をすべきですか？',
  reviewPlaybookStepsPrompt: 'プレイブックステップを確認して、改善案を提案できますか？',
  playbookConversation: 'プレイブック会話',

  // Workspace Loading
  workspaceNotFound: 'ワークスペースが見つかりません',
  failedToLoadWorkspace: 'ワークスペースの読み込みに失敗しました',
  loadingWorkspace: 'ワークスペースを読み込み中...',
  rateLimitExceeded: 'レート制限を超えました。{seconds} 秒待ってからページを更新してください。',
  retryButton: '再試行',

  // Timeline Panel
  returnToWorkspaceOverview: 'ワークスペース概要に戻る',
  currentExecution: '現在の実行',
  otherExecutionsOfSamePlaybook: '同じプレイブックの他の実行',
  otherPlaybooksExecutions: '他のプレイブックの実行',
  recentFailures: '最近の失敗',

  // Execution Chat
  discussPlaybookExecution: 'このプレイブック実行について AI と議論する...',
  itKnowsStepsEventsErrors: 'ステップ、イベント、エラーを知っています。',
  executionChatDescription: 'これは実行ステータスを尋ねたり、ステップを理解したり、提案を得るためのディスカッションパネルです。操作（再試行、キャンセルなど）が必要な場合は、メイン実行インターフェースのボタンを使用してください。',
  recommended: '（推奨）',
  autoStart: '自動開始：',
  aiThinking: 'AIが考えています...',
} as const satisfies Partial<Record<MessageKey, string>>;

