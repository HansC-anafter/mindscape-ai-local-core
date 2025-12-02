/**
 * Execution i18n messages (Traditional Chinese)
 * Playbook execution, workspace execution inspector, and related UI
 */
import type { MessageKey } from '../../keys';

export const executionZhTW = {
  // Playbook Execution Inspector
  runInsightDraftChanges: '執行洞察與草稿變更',
  reviewAISuggestions: '檢視 AI 建議並套用變更以改善此工作劇本',
  aiAnalysis: 'AI 分析',
  apply: '套用',
  discard: '捨棄',
  step: '步驟',
  noRevisionSuggestions: '尚無修訂建議。',
  chatWithPlaybookInspector: '與工作劇本檢查器對話以取得建議。',
  revisionDraft: '修訂草稿',
  aiSuggestedChangesWillAppear: 'AI 建議的變更將顯示於此',
  stepsTimeline: '步驟時間軸',
  eventStream: '事件串流',
  noEventsYet: '尚無事件',
  toolCalls: '工具呼叫',
  selectStepToViewDetails: '選擇步驟以查看詳情',
  editPlaybook: '編輯工作劇本',

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

  // Execution Header
  runNumber: '執行 #{number}',
  stepProgress: '步驟 {current} / {total}',
  startedAt: '開始於 {time}',
  byUser: '由 {user}',
  unknownUser: '未知使用者',
  unknownPlaybook: '未知工作劇本',
  errorLabel: '錯誤：',

  // Step Details
  noEvents: '尚無事件',
  agent: '代理：',
  tool: '工具：',
  collaboration: '協作：',
  startingPlaybookExecution: '開始執行 Playbook：{playbook}',
  stepNumber: '步驟 {number}',
  unnamed: '未命名',
  tools: '工具',

  // Execution Messages
  thisExecutionFailed: '此執行失敗：{reason}。請檢視步驟時間軸以識別問題。',

  // Playbook Inspector
  playbookInspector: '工作劇本檢查器',
  playbookRun: '工作劇本 - 執行 #{number}',
  askPlaybookInspector: '詢問工作劇本檢查器關於此次執行。它知道步驟、事件和錯誤。',
  explainWhyFailed: '解釋為何此次執行失敗',
  suggestNextSteps: '建議下一步',
  reviewPlaybookSteps: '檢視工作劇本步驟',
  explainWhyFailedPrompt: '你能解釋為什麼這次執行失敗了嗎？出了什麼問題，我該如何修復？',
  explainWhyFailedPromptAlt: '這次執行的當前狀態是什麼？',
  suggestNextStepsPrompt: '我接下來應該做什麼來解決這個問題或繼續執行？',
  reviewPlaybookStepsPrompt: '你能檢視工作劇本步驟並建議任何改進嗎？',
  playbookConversation: '工作劇本對話',

  // Workspace Loading
  workspaceNotFound: '找不到工作區',
  failedToLoadWorkspace: '載入工作區失敗',
  loadingWorkspace: '載入工作區中...',
  rateLimitExceeded: '超過速率限制。請等待 {seconds} 秒後重新整理頁面。',
  retryButton: '重試',

  // Timeline Panel
  returnToWorkspaceOverview: '返回工作區概覽',
  currentExecution: '目前執行',
  otherExecutionsOfSamePlaybook: '同工作劇本的其他執行',
  otherPlaybooksExecutions: '其他工作劇本執行',
  recentFailures: '最近的失敗',

  // Execution Chat
  discussPlaybookExecution: '與 AI 討論此工作劇本執行...',
  itKnowsStepsEventsErrors: '它知道步驟、事件和錯誤。',
  executionChatDescription: '這是討論面板，用於詢問執行狀態、理解步驟內容或獲得建議。如需操作（重試、取消等），請使用主執行介面的按鈕。',
  recommended: '（推薦）',
  autoStart: '自動啟動：',
  aiThinking: 'AI 正在思考...',
} as const satisfies Partial<Record<MessageKey, string>>;

