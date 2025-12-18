/**
 * workspace i18n messages (Japanese)
 */
import type { MessageKey } from '../../keys';

export const workspaceJa = {
  // Workspace creation wizard
  createWorkspace: 'ワークスペースを作成',
  selectCreationMethod: '作成方法を選択',
  quickCreate: 'クイック作成',
  quickCreateDescription: '名前のみ入力、すぐに開始',
  llmGuidedCreate: 'LLM ガイド作成',
  llmGuidedCreateDescription: 'AI がワークスペース設定を支援',
  workspaceName: 'ワークスペース名',
  workspaceNameRequired: 'ワークスペース名 *',
  workspaceDescription: 'ワークスペース説明',
  workspaceDescriptionRequired: 'ワークスペース説明（必須）',
  workspaceDescriptionOptional: '説明（任意）',
  workspaceNamePlaceholder: '例：プロジェクト管理、日常タスクなど',
  workspaceDescriptionPlaceholder: 'このワークスペースの目的を記述...',
  workspaceDescriptionLLMPlaceholder: 'ワークスペースの目的、目標、ワークフローを記述...',
  addReferenceSeed: '参照シードを追加（任意）',
  addReferenceSeedDescription: '任意、後で追加可能',
  pasteText: 'テキストを貼り付け',
  pasteTextPlaceholder: '要件または説明を貼り付け...',
  createAndComplete: '作成して完了',
  pleaseSelectCreationMethod: 'まず作成方法を選択してください',
  back: '戻る',
  next: '次へ',
  previous: '前へ',

  // Workspace launchpad
  workspaceBrief: 'workspaceBrief',
  firstPlaybook: 'firstPlaybook',
  recommendedPlaybook: 'recommendedPlaybook',
  runFirstPlaybook: 'runFirstPlaybook',
  startWork: 'startWork',
  startWorkDescription: 'startWorkDescription',
  openWorkspace: 'openWorkspace',
  nextIntents: 'nextIntents',
  items: '件',
  toolConnections: 'ツール接続',
  editBlueprint: 'editBlueprint',

  // Workspace status
  ready: '準備完了',
  pending: '保留中',
  active: 'アクティブ',

  // Workspace empty state
  workspaceNotConfigured: 'ワークスペース未設定',
  workspaceNotConfiguredDescription: '初期設定が必要。「最小ファイル参照」を使用するか手動で設定。',
  configureWorkspace: 'ワークスペースを設定',
  startWorkDirectly: '直接作業を開始',

  // Setup drawer
  assembleWorkspace: 'ワークスペースを組み立て',
  minimumFileReference: '最小ファイル参照 (MFR)',
  minimumFileReferenceDescription: 'クイック設定：テキスト貼り付け、ファイルアップロード、URL 貼り付けで自動生成。',
  referenceTextToStartWorkspace: '参照テキストでワークスペースを開始',
  close: '閉じる',
  processing: '処理中...',
  workspaceConfigured: 'ワークスペース設定完了！',
  configurationFailed: '設定失敗：',
  creationFailed: '作成失敗：',

  // Other methods (coming soon)
  otherMethods: 'その他の方法（近日公開）：',
  uploadFile: '📄 ファイルをアップロード',
  pasteUrl: '🔗 URL を貼り付け',

  // Error messages
  errorLoadingWorkspace: 'ワークスペース読み込みエラー',
  workspaceNotFound: 'ワークスペースが見つかりません',
  loadingWorkspace: 'ワークスペースを読み込み中...',
} as const satisfies Partial<Record<MessageKey, string>>;

