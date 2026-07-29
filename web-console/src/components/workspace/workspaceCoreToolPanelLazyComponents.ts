import { lazyWorkspaceToolPanel } from './lazyWorkspaceToolPanel';

export const WorkspaceRunsPanel = lazyWorkspaceToolPanel(
  () => import('@/app/workspaces/[workspaceId]/capability-ui-hosts/WorkspaceRunsPanel'),
);
export const WorkspaceSettingsToolPanel = lazyWorkspaceToolPanel(
  () => import('@/app/workspaces/[workspaceId]/capability-ui-hosts/WorkspaceSettingsToolPanel'),
);
export const WorkspacePackToolPanel = lazyWorkspaceToolPanel(
  () => import('@/app/workspaces/[workspaceId]/capability-ui-hosts/WorkspacePackToolPanel'),
);
export const MotionSourceRailPanel = lazyWorkspaceToolPanel(
  () => import('@/components/workspace/device-binding/MotionSourceRailPanel'),
);
