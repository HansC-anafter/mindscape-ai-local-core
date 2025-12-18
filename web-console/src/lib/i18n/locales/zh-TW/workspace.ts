/**
 * workspace i18n messages (Traditional Chinese)
 */
import type { MessageKey } from '../../keys';

export const workspaceZhTW = {
  // Workspace creation wizard
  createWorkspace: '建立工作區',
  selectCreationMethod: '選擇建立方式',
  quickCreate: '快速建立',
  quickCreateDescription: '只輸入名稱，快速開始',
  llmGuidedCreate: 'LLM 引導建立',
  llmGuidedCreateDescription: '讓 AI 協助你配置工作區',
  workspaceName: '工作區名稱',
  workspaceNameRequired: '工作區名稱 *',
  workspaceDescription: '工作區描述',
  workspaceDescriptionRequired: '工作區描述（必填）',
  workspaceDescriptionOptional: '說明（選填）',
  workspaceNamePlaceholder: '例如：專案管理、日常任務等',
  workspaceDescriptionPlaceholder: '描述這個工作區的用途...',
  workspaceDescriptionLLMPlaceholder: '描述工作區用途、目標與工作流程...',
  addReferenceSeed: '加一個引用種子（可跳過）',
  addReferenceSeedDescription: '可選，稍後再補',
  pasteText: '貼上文字',
  pasteTextPlaceholder: '貼上需求或描述...',
  createAndComplete: '建立並完成',
  pleaseSelectCreationMethod: '請先選擇建立方式',
  back: '返回',
  next: '下一步',
  previous: '上一步',

  // Workspace launchpad
  workspaceBrief: 'workspaceBrief',
  firstPlaybook: 'firstPlaybook',
  recommendedPlaybook: 'recommendedPlaybook',
  runFirstPlaybook: 'runFirstPlaybook',
  startWork: 'startWork',
  startWorkDescription: 'startWorkDescription',
  openWorkspace: 'openWorkspace',
  nextIntents: 'nextIntents',
  items: '個',
  toolConnections: 'Tool Connections',
  editBlueprint: 'editBlueprint',

  // Workspace status
  ready: 'Ready',
  pending: 'Pending',
  active: 'Active',

  // Workspace empty state
  workspaceNotConfigured: '工作區尚未配置',
  workspaceNotConfiguredDescription: '需要初始設定。使用「最小文件引用」或手動配置。',
  configureWorkspace: '配置工作區',
  startWorkDirectly: '直接開始工作',

  // Setup drawer
  assembleWorkspace: '組裝工作區',
  minimumFileReference: '最小文件引用 (MFR)',
  minimumFileReferenceDescription: '快速設定：貼上文字、上傳檔案或貼上網址，自動生成藍圖。',
  referenceTextToStartWorkspace: '引用文字開啟工作區',
  close: '關閉',
  processing: '處理中...',
  workspaceConfigured: '工作區已配置完成！',
  configurationFailed: '配置失敗：',
  creationFailed: '建立失敗：',

  // Other methods (coming soon)
  otherMethods: '其他方式（即將推出）：',
  uploadFile: '📄 上傳檔案',
  pasteUrl: '🔗 貼上網址',

  // Error messages
  errorLoadingWorkspace: 'Error Loading Workspace',
  workspaceNotFound: 'Workspace not found',
  loadingWorkspace: 'Loading workspace...',
} as const satisfies Partial<Record<MessageKey, string>>;


