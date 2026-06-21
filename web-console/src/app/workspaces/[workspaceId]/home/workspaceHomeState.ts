import type {
  LaunchpadData,
  WorkspaceHomeDerivedState,
  WorkspaceHomeWorkspace,
  WorkspaceWizardData,
} from './workspaceHomeTypes';

export function hasLaunchpadContent(launchpadData: LaunchpadData | null): boolean {
  if (!launchpadData) {
    return false;
  }

  return Boolean(
    (launchpadData.brief && launchpadData.brief.trim().length > 0) ||
      (launchpadData.initial_intents && launchpadData.initial_intents.length > 0) ||
      (launchpadData.tool_connections && launchpadData.tool_connections.length > 0)
  );
}

export function deriveWorkspaceHomeState(
  launchpadData: LaunchpadData | null,
  workspace: WorkspaceHomeWorkspace | null
): WorkspaceHomeDerivedState {
  const launchStatus = launchpadData?.launch_status || workspace?.launch_status || 'pending';
  const hasActualContent = hasLaunchpadContent(launchpadData);
  const isPending = launchStatus === 'pending' && !hasActualContent;
  const isReady = launchStatus === 'ready' || (launchStatus === 'pending' && hasActualContent);
  const hasContent = hasActualContent || (!isPending && Boolean(launchpadData));

  return {
    launchStatus,
    hasActualContent,
    isPending,
    isReady,
    hasContent,
  };
}

export function canCompleteWorkspaceWizard(wizardData: WorkspaceWizardData): boolean {
  if (wizardData.method === 'quick') {
    return Boolean(wizardData.title);
  }
  if (wizardData.method === 'llm-guided') {
    return Boolean(wizardData.title && wizardData.description);
  }
  return false;
}
