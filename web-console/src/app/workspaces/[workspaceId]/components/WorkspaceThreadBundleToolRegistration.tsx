'use client';

import React from 'react';
import { Box } from 'lucide-react';

import {
  useWorkspaceGlobalToolContributions,
  useWorkspaceGlobalToolRail,
  type WorkspaceGlobalToolContribution,
} from './useWorkspaceGlobalToolRail';

const ThreadBundlePanel = React.lazy(() => import('@/components/workspace/ThreadBundlePanel').then((module) => ({
  default: module.ThreadBundlePanel,
})));

interface WorkspaceThreadBundleToolRegistrationProps {
  workspaceId: string;
  apiUrl: string;
  selectedThreadId: string | null;
}

export default function WorkspaceThreadBundleToolRegistration({
  workspaceId,
  apiUrl,
  selectedThreadId,
}: WorkspaceThreadBundleToolRegistrationProps) {
  const { setActiveToolKey } = useWorkspaceGlobalToolRail();
  const contributions = React.useMemo<WorkspaceGlobalToolContribution[]>(() => {
    if (!selectedThreadId) {
      return [];
    }
    return [{
      key: 'core:bundle',
      id: 'bundle',
      label: 'Bundle',
      icon: <Box aria-hidden="true" className="h-4 w-4" />,
      group: 'workspace',
      order: 50,
      testId: 'workspace-bundle-tool',
      renderPanel: () => (
        <ThreadBundlePanel
          threadId={selectedThreadId}
          workspaceId={workspaceId}
          isOpen
          onClose={() => setActiveToolKey(null)}
          apiUrl={apiUrl}
          embedded
        />
      ),
    }];
  }, [apiUrl, selectedThreadId, setActiveToolKey, workspaceId]);

  useWorkspaceGlobalToolContributions('workspace-thread-bundle', contributions);

  return null;
}
