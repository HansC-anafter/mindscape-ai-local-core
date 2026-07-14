export type SettingsSection = 'Status' | 'Workspace' | 'Remote Access' | 'Execution' | 'Tools' | 'Social' | 'Data';

export interface WorkspaceSettingsToolPanelProps {
  workspaceId: string;
  apiUrl: string;
}
