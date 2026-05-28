import React from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ExecutionPage from './page';

vi.mock('next/navigation', () => ({
  useParams: () => ({
    workspaceId: 'ws_test',
    executionId: 'exec_test',
  }),
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock('../../../../../lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/i18n', () => ({
  useT: () => (() => null),
}));

vi.mock('@/contexts/WorkspaceDataContext', async () => {
  return {
    useWorkspaceData: () => ({
      workspace: {
        id: 'ws_test',
        title: 'Workspace Test',
        primary_project_id: null,
        data_sources: [],
      },
    }),
  };
});

vi.mock('@/hooks/useExecutionState', () => ({
  useExecutionState: () => ({
    trainSteps: [],
    overallProgress: 0,
    isExecuting: false,
  }),
}));

vi.mock('../../../components/ExecutionInspector', async () => {
  const ReactModule = await import('react');
  return {
    default: () => ReactModule.createElement('div', { 'data-testid': 'execution-inspector' }, 'Inspector'),
  };
});

vi.mock('../../../components/ExecutionChatPanel', async () => {
  const ReactModule = await import('react');
  return {
    default: () => ReactModule.createElement('div', { 'data-testid': 'execution-chat-panel' }, 'Chat'),
  };
});

vi.mock('../../../components/TimelinePanel', async () => {
  const ReactModule = await import('react');
  return {
    default: () => ReactModule.createElement('div', { 'data-testid': 'timeline-panel' }, 'Timeline'),
  };
});

vi.mock('@/components/execution', async () => {
  const ReactModule = await import('react');
  return {
    ExecutionSidebar: () => ReactModule.createElement('div', { 'data-testid': 'execution-sidebar' }, 'Executions'),
    TrainHeader: () => ReactModule.createElement('div', { 'data-testid': 'train-header' }, 'Train'),
  };
});

describe('ExecutionPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => undefined)));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('keeps Pack and workspace settings out of the execution left sidebar', () => {
    render(<ExecutionPage />);

    expect(screen.getByRole('button', { name: /Scheduling/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Outcomes/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Pack/ })).toBeNull();
    expect(screen.queryByText('Workspace Settings')).toBeNull();
  });
});
