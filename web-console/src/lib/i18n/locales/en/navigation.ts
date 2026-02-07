/**
 * navigation i18n messages (English)
 */
import type { MessageKey } from '../../keys';

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
  switchToLightMode: 'Switch to Light Mode',
  switchToDarkMode: 'Switch to Dark Mode',
  workspaceList: 'Workspace List',
  backToWorkspace: 'Back to Workspace',

} as const satisfies Partial<Record<MessageKey, string>>;
