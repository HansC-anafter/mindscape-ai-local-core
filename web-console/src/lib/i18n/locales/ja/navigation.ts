/**
 * Navigation i18n messages (Japanese)
 * Navigation menu items and routes
 */
import type { MessageKey } from '../../keys';

export const navigationJa = {
  // Navigation
  navWorkspaces: 'ワークスペース',
  workspace: 'ワークスペース',
  backToWorkspaces: 'ワークスペース一覧に戻る',
  pendingTasks: '保留中のタスク',
  navMindscape: 'マインドスケープ',
  navPlaybooks: 'プレイブック',
  navProfile: 'プロフィール',
  navIntents: '意図カード',
  navAgents: 'AI チーム',
  navRunAgent: 'AI チームを起動',
  navHistory: '実行履歴',
  navSystem: 'システム管理',
  navSettings: '設定',
} as const satisfies Partial<Record<MessageKey, string>>;

