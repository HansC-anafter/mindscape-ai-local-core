export type SettingsSection = 'Status' | 'Workspace' | 'Execution' | 'Tools' | 'Social' | 'Data';

export interface WorkspaceSettingsToolPanelProps {
  workspaceId: string;
  apiUrl: string;
}
