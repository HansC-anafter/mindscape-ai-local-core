/**
 * Execution i18n messages (Traditional Chinese)
 * Playbook execution, workspace execution inspector, and related UI
 */
import type { MessageKey } from '../../keys';

export const executionZhTW = {
  // Playbook Execution Inspector
  runInsightDraftChanges: '執行洞察與草案變更',
  reviewAISuggestions: '審查 AI 建議並套用變更以改進此 Playbook',
  aiAnalysis: 'AI 分析',
  apply: '套用',
  discard: '捨棄',
  step: '步驟',
  noRevisionSuggestions: '目前尚無修正建議。',
  chatWithPlaybookInspector: '與 Playbook 檢查器聊天以獲取建議。',
  revisionDraft: '修正草案',
  aiSuggestedChangesWillAppear: 'AI 建議的變更將在此顯示',
  stepsTimeline: '步驟時間軸',
  eventStream: '事件串流',
  noEventsYet: '目前尚無事件',
  toolCalls: '工具呼叫',
  selectStepToViewDetails: '選擇步驟以查看詳細資訊',
  editPlaybook: '編輯 Playbook',

  // Execution Status
  executionStatusRunning: '執行中',
  executionStatusSucceeded: '成功',
  executionStatusFailed: '失敗',
  executionStatusPaused: '已暫停',
  executionStatusUnknown: '未知',

  // Trigger Source
  triggerSourceAuto: '自動',
  triggerSourceSuggested: '建議',
  triggerSourceManual: '手動',
  triggerSourceUnknown: '未知',

  // Actions
  stop: '停止',
  stopping: '停止中...',
  reload: '重新載入',
  reloading: '重新載入中...',
  restart: '重新開始',
  restarting: '重新開始中...',
  reloadPlaybook: '重新載入 Playbook',
  restartExecution: '重新開始執行',
  confirmRestartExecution: '確定要重新開始此執行嗎？\n\n這將從頭開始創建一個新的執行並取消當前執行。',
  restartingExecution: '正在重新開始執行，請稍候...',
  executionRestarted: '執行已重新開始',
  executionRestartFailed: '執行重新開始失敗',
  view: '查看',

  // Execution Header
  runNumber: '執行 #{number}',
  stepProgress: '步驟 {current} / {total}',
  startedAt: '開始時間 {time}',
  byUser: '使用者：{user}',
  unknownUser: '未知使用者',
  unknownPlaybook: '未知 Playbook',
  errorLabel: '錯誤：',

  // Step Details
  noEvents: '目前尚無事件',
  agent: '代理：',
  tool: '工具：',
  collaboration: '協作：',
  startingPlaybookExecution: '開始 Playbook 執行：{playbook}',
  stepNumber: '步驟 {number}',
  unnamed: '未命名',
  tools: '工具',
  pending: '待處理',

  // Execution Messages
  thisExecutionFailed: '此執行失敗：{reason}。請查看步驟時間軸以診斷問題。',

  // Playbook Inspector
  playbookInspector: 'Playbook 檢查器',
  playbookRun: 'Playbook - 執行 #{number}',
  askPlaybookInspector: '請詢問 Playbook 檢查器關於此執行的問題。它知道步驟、事件和錯誤。',
  explainWhyFailed: '說明此執行失敗的原因',
  suggestNextSteps: '建議下一步',
  reviewPlaybookSteps: '審查 Playbook 步驟',
  explainWhyFailedPrompt: '能否說明此執行失敗的原因？問題是什麼，如何修正？',
  explainWhyFailedPromptAlt: '此執行的目前狀態是什麼？',
  suggestNextStepsPrompt: '應該如何解決此問題或繼續執行？',
  reviewPlaybookStepsPrompt: '能否審查 Playbook 步驟並提供改進建議？',
  playbookConversation: 'Playbook 對話',

  // Workspace Loading
  workspaceNotFound: '找不到工作空間',
  failedToLoadWorkspace: '載入工作空間失敗',
  loadingWorkspace: '載入工作空間中...',
  rateLimitExceeded: '已超過速率限制。請等待 {seconds} 秒後重新整理頁面。',
  retryButton: '重試',

  // Timeline Panel
  returnToWorkspaceOverview: '返回工作空間總覽',
  currentExecution: '目前執行',
  otherExecutionsOfSamePlaybook: '相同 Playbook 的其他執行',
  otherPlaybooksExecutions: '其他 Playbook 的執行',
  recentFailures: '最近的失敗',

  // Execution Chat
  discussPlaybookExecution: '與 AI 討論此 Playbook 執行...',
  itKnowsStepsEventsErrors: '它知道步驟、事件和錯誤。',
  executionChatDescription: '這是一個討論面板，可用於詢問執行狀態、理解步驟或獲取建議。如需操作（重試、取消等），請使用主執行介面的按鈕。',
  recommended: '（推薦）',
  autoStart: '自動開始：',
  aiThinking: 'AI 思考中...',
} as const satisfies Partial<Record<MessageKey, string>>;

