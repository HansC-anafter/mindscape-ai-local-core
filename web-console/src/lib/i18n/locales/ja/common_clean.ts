/**
 * Common i18n messages (Japanese)
 * Shared across all modules
 */

import type { MessageKey } from '../../keys';

export const commonJa = {
  // Status
  status: 'ステータス',
  statusActive: '進行中',
  statusCompleted: '完了',
  statusIdentified: '識別済み',
  statusPendingAdd: '追加待ち',
  statusAdded: '追加済み',
  statusPaused: '一時停止',
  statusArchived: 'アーカイブ済み',

  // Priority
  priorityLow: '低',
  priorityMedium: '中',
  priorityHigh: '高',
  priorityCritical: '緊急',

  // Actions
  save: '保存',
  cancel: 'キャンセル',
  delete: '削除',
  edit: '編集',
  create: '作成',
  update: '更新',
  search: '検索',
  add: '追加',
  accept: '受け入れる',
  skip: 'スキップ',
  copy: 'コピー',
  open: '開く',
  download: 'ダウンロード',
  sourceIntent: 'ソースインテント',
  noOutcomes: '成果なし',

  // Common
  loading: '読み込み中...',
  saving: '保存中...',
  error: 'エラーが発生しました',
  success: '成功',
  noData: 'データなし',
  notice: '注意',
  hint: 'ヒント',
  times: '回',
  retryFailed: '再試行失敗',
  unknownError: '不明なエラー',
  storageLocationNotSpecified: 'ストレージの場所が指定されていません',
  actionRequired: '対応が必要',
  configureStoragePathNow: 'ストレージパスを今すぐ設定',
  retryArtifactCreation: '成果物の作成を再試行',
  llmConfidenceScore: 'LLM 分析信頼度: {confidence} (範囲: 0~1)',

  // Tool integration categories
  requiresExternalSetup: '外部設定が必要',
  generalIntegrations: '一般統合',
  generalIntegrationsLocalDescription: 'ローカルコアモードで動作する一般的なツール統合',
  generalIntegrationsDescription: '一般的なツール統合',
  developerIntegrations: '開発者統合',
  developerIntegrationsDescription: '外部環境または技術協力が必要な高度な統合、主に技術パートナー向け',

  // Pending Tasks
  intentBasedOnAISuggestion: 'AI 提案に基づく意図：',
  editIntentLabel: '意図ラベルを編集',
  backgroundExecution: 'バックグラウンド実行',
  backgroundExecutionDescription: 'このタスクはバックグラウンドで自動実行され、LLM 分析は不要です',
  enableBackgroundTask: 'バックグラウンドタスクを有効化',
  enableFailed: '有効化失敗',
  confidence: '信頼度：',
  executionSuccessUpdating: '実行成功、更新中...',

  // Status and states
  disabled: '無効',
  enabled: '有効',
  runningNormally: '正常に実行中',
  executionFailed: '実行失敗',
  noBackgroundTasks: 'バックグラウンドタスクがありません',
  processing: '処理中...',
  disable: '無効化',
  enable: '有効化',
  lastExecution: '前回の実行：',
  nextExecution: '次の実行：',
  lastExecutionFailed: '最後の実行が失敗しました',
  operationFailed: '操作失敗',

  // Execution flow
  executionAISuggested: 'AI 提案',
  executionRequiresConfirmation: '確認が必要',
  executionSelectStepForDetails: '詳細を表示するステップを選択してください',
  executionCancel: 'キャンセル',
  executionSummary: '実行概要',
  executionWaitingConfirmation: '確認待ち',
  executionConfirmationMessage: 'このステップを続けるには確認が必要です',
  executionConfirmContinue: '確認して続行',
  executionReject: '拒否',

  // Timeline management
  timelineRunning: '実行中',
  timelinePendingConfirmation: '確認待ち',
  timelineArchived: 'アーカイブ済み',
  timelineHistory: '履歴',
  noRunningExecutions: '実行中のスケジュールはありません',
  noPendingConfirmations: '確認待ちのスケジュールはありません',
  noArchivedExecutions: 'アーカイブ済みのスケジュールはありません',
  retry: '再試行',
  viewArtifact: '成果を表示',
  timelineItemNotFound: '関連する Timeline Item が見つかりません',
  timelineItemUnavailable: 'Timeline Item を取得できません',

  // Tool status labels
  statusNotConfigured: '未設定',
  statusNotConnected: '未接続',
  statusConnected: '接続済み',
  statusEnabled: '有効',
  statusDisabled: '無効',
  statusLocalMode: 'ローカルモード',
  statusNotSupported: 'サポートされていません',
  nextStep: '次のステップ',
  startedAt: '開始時刻',

  // Sidebar and navigation
  tabScheduling: 'スケジュール',
  tabOutcomes: '成果',
  tabBackgroundTasks: 'バックグラウンドタスク',
  backgroundTasksPanel: 'バックグラウンドタスクパネル',
  running: '実行中',
  pending: '待機中',
  createdAt: '作成時刻',
  activeExecutions: '実行中のタスク',
  backgroundRoutines: 'バックグラウンドタスク',
  systemTools: 'システムツール',
  systemTool: 'システムツール',

  // Modal and UI components
  configureTool: 'ツールを設定',
  configureWorkflow: 'ワークフローを設定',
  editMCPServer: 'MCP サーバーを編集',
  addMCPServer: 'MCP サーバーを追加',
  closeModal: 'モーダルを閉じる',
  unsupportedToolType: 'サポートされていないツールタイプ',
  closeButton: '閉じる',

  // Copy actions
  copyAll: 'すべてコピー',
  copyAllMessages: 'すべてのメッセージをコピー',
  copyMessage: 'メッセージをコピー',
  copied: 'コピーしました',
  user: 'ユーザー',
  assistant: 'アシスタント',

  // System messages and errors
  disconnected: '切断されました',
  confirmDelete: '削除の確認',
  deleting: '削除中',
  failedToLoad: '読み込みに失敗しました',
  dimensions: '寸法',
  contextWindow: 'コンテキストウィンドウ',
  executionStatusCancelled: 'キャンセルされました',

  // Additional status and actions
  ready: '準備完了',
  needsSetup: '設定が必要',
  unsupported: 'サポートされていません',
  toolsNeedConfiguration: 'ツールの設定が必要',
  requiredToolsNotSupported: '必要なツールがサポートされていません',
} as const satisfies Partial<Record<MessageKey, string>>;
