import React from 'react';
import { vi } from 'vitest';

import {
  useCapabilityWorkbenchInfoMetadataRegistration,
} from '@/components/capabilities/workbench/CapabilityWorkbenchInfoProvider';
import type { CapabilityWorkbenchInfoMetadata } from '@/types/capability-workbench';

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/page-visibility', () => ({
  isDocumentHidden: () => false,
}));

vi.mock('@/lib/navigation/openAppRouteInNewWindow', () => ({
  openAppRouteInNewWindow: vi.fn(),
}));

vi.mock('@/lib/i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/i18n')>();
  return {
    ...actual,
    useT: () => ((key: string) => (key === 'workspacePackTool' ? 'Pack' : null)),
  };
});

vi.mock('next/navigation', () => ({
  usePathname: () => '/workspaces/ws_test/capability-ui-hosts/demo_capability',
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/workspace-tools/workspace-tool-registry', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/workspace-tools/workspace-tool-registry')>();
  return {
    ...actual,
    fetchWorkspaceToolDefinitions: vi.fn(async () => []),
  };
});

vi.mock('@/lib/capability-ui-loader', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/capability-ui-loader')>();
  const ReactModule = await import('react');
  return {
    ...actual,
    loadCapabilityUIComponent: vi.fn(async () => function MockIGRunsWorkspaceToolPanel({
      workspaceId,
    }: {
      workspaceId: string;
    }) {
      ReactModule.useEffect(() => {
        void fetch(`/api/v1/ig/workbench/sidebar-summary?workspace_id=${workspaceId}`);
      }, [workspaceId]);
      return ReactModule.createElement('div', { 'data-testid': 'ig-runs-adapter' }, 'IG runs');
    }),
  };
});

vi.mock('./WorkspacePackToolPanel', async () => {
  const ReactModule = await import('react');
  return {
    default: ({ workspaceId }: { workspaceId: string }) => ReactModule.createElement(
      'div',
      { 'data-testid': 'workspace-pack-tool-panel' },
      `Pack panel ${workspaceId}`,
    ),
  };
});

vi.mock('@/lib/workspace-runs/useRunObservationsSummary', () => ({
  useRunObservationsSummary: vi.fn(() => ({
    summary: null,
    isLoading: false,
    error: null,
    externalActiveCount: 0,
  })),
}));

vi.mock('@/contexts/WorkspaceDataContext', () => ({
  WorkspaceDataProvider: ({
    children,
    initialLoadProfile,
  }: {
    children: React.ReactNode;
    initialLoadProfile?: string;
  }) => (
    <div data-testid="workspace-data-provider" data-initial-load-profile={initialLoadProfile || 'full'}>
      {children}
    </div>
  ),
  useWorkspaceDataOptional: () => ({
    executions: [
      {
        id: 'exec_running',
        status: 'running',
        playbook_code: 'ig_complete_workflow',
      },
      {
        id: 'exec_done',
        status: 'completed',
        playbook_code: 'ig_post_generation',
      },
    ],
  }),
}));

vi.mock('@/contexts/ExecutionContextContext', () => ({
  ExecutionContextProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="execution-context-provider">{children}</div>
  ),
}));

export const WORKBENCH_METADATA: CapabilityWorkbenchInfoMetadata = {
  schemaVersion: 'capability_workbench_info_metadata.v1',
  capability: {
    code: 'demo_capability',
    label: 'Demo Capability',
  },
  workspace: {
    id: 'ws_test',
  },
  primaryObject: {
    kind: 'artifact',
    id: 'asset_test',
    label: 'Asset test',
  },
  session: {
    id: 'session_route_001',
    kind: 'demo_session',
    status: 'active',
  },
  artifact: {
    id: 'artifact_test',
    kind: 'demo_artifact',
  },
  selection: {
    sceneId: 'item01',
    mode: 'inspect',
    department: 'review',
  },
  references: [
    {
      key: 'asset',
      label: 'Asset',
      value: 'asset_test',
      copyValue: 'asset_test',
    },
  ],
  status: [
    {
      key: 'preview_state',
      label: 'Preview state',
      value: 'idle',
      tone: 'neutral',
    },
  ],
};

export function WorkbenchMetadataRegistration() {
  useCapabilityWorkbenchInfoMetadataRegistration(WORKBENCH_METADATA);
  return <div data-testid="surface-content">Capability surface</div>;
}
