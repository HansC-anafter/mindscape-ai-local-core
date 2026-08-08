export type SettingsSection = 'Status' | 'Workspace' | 'Members & access' | 'Execution' | 'Tools' | 'Social' | 'Data';

export interface WorkspaceSettingsToolPanelProps {
  workspaceId: string;
  apiUrl: string;
}
