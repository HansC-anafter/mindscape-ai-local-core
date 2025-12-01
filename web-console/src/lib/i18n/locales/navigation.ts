/**
 * Navigation i18n messages
 * Navigation menu items and routes
 */
import type { MessageKey } from '../keys';

export const navigationZhTW = {
  // Navigation
  navWorkspaces: '工作區',
  workspace: '工作區',
  backToWorkspaces: '返回工作區列表',
  pendingTasks: '待處理任務',
  navMindscape: '心智空間',
  navPlaybooks: '工作劇本庫',
  navProfile: '自我設定',
  navIntents: '意圖卡',
  navAgents: 'AI 團隊',
  navRunAgent: '啟動 AI 團隊',
  navHistory: '執行記錄',
  navSystem: '系統管理',
  navSettings: '設定',
} as const satisfies Partial<Record<MessageKey, string>>;

export const navigationEn = {
  // Navigation
  navWorkspaces: 'Workspaces',
  workspace: 'Workspace',
  backToWorkspaces: 'Back to Workspaces',
  pendingTasks: 'Pending Tasks',
  navMindscape: 'Mindscape',
  navPlaybooks: 'Playbooks',
  navProfile: 'Profile',
  navIntents: 'Intent Cards',
  navAgents: 'AI Team',
  navRunAgent: 'Run AI Team',
  navHistory: 'History',
  navSystem: 'System Management',
  navSettings: 'Settings',
} as const satisfies Partial<Record<MessageKey, string>>;
