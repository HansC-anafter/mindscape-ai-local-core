import { fireEvent, render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import React from 'react';
import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';

import type { ThreadBundle } from '@/hooks/useThreadBundle';

import { ThreadBundlePanel } from './ThreadBundlePanel';
import {
  addThreadReference,
  buildThreadReferenceUrl,
} from './threadBundlePanel/referenceActions';

const hookMock = vi.hoisted(() => ({
  useThreadBundle: vi.fn(),
}));

vi.mock('@/hooks/useThreadBundle', () => ({
  useThreadBundle: hookMock.useThreadBundle,
}));

const sampleBundle: ThreadBundle = {
  thread_id: 'thread-1',
  overview: {
    title: 'Thread title',
    status: 'in_progress',
    summary: 'Bundle summary',
    labels: [],
  },
  deliverables: [{
    id: 'deliverable-1',
    title: 'Deliverable One',
    artifact_type: 'document',
    source: 'playbook',
    source_event_id: 'event-1',
    status: 'draft',
    updated_at: '2026-06-21T00:00:00Z',
  }],
  references: [{
    id: 'reference-1',
    source_type: 'url',
    uri: 'https://example.test/reference',
    title: 'Reference One',
    snippet: 'Reference summary',
    reason: 'Useful context',
    created_at: '2026-06-21T00:00:00Z',
    pinned_by: 'user',
  }],
  runs: [{
    id: 'run-1',
    playbook_name: 'Run One',
    status: 'completed',
    started_at: '2026-06-21T00:00:00Z',
    duration_ms: 1200,
    steps_completed: 2,
    steps_total: 2,
    deliverable_ids: ['deliverable-1'],
    result_summary: 'Run summary',
    storage_ref: 'storage://run-1',
  }],
  sources: [{
    id: 'source-1',
    type: 'wordpress_site',
    identifier: 'site-1',
    display_name: 'Source One',
    permissions: ['read'],
    sync_status: 'connected',
  }],
};

const workspaceRoot = process.cwd();
const componentDir = path.join(workspaceRoot, 'src/components/workspace');
const panelDir = path.join(componentDir, 'threadBundlePanel');

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('ThreadBundlePanel', () => {
  it('does not render when closed', () => {
    hookMock.useThreadBundle.mockReturnValue({
      bundle: sampleBundle,
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    const { container } = render(
      <ThreadBundlePanel
        apiUrl="http://api.test"
        isOpen={false}
        threadId="thread-1"
        workspaceId="workspace-1"
        onClose={vi.fn()}
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  it('keeps the public wrapper compatible with useThreadBundle and section navigation', () => {
    hookMock.useThreadBundle.mockReturnValue({
      bundle: sampleBundle,
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    render(
      <ThreadBundlePanel
        apiUrl="http://api.test"
        embedded
        isOpen
        threadId="thread-1"
        workspaceId="workspace-1"
        onClose={vi.fn()}
      />,
    );

    expect(hookMock.useThreadBundle).toHaveBeenCalledWith('workspace-1', 'thread-1', 'http://api.test');
    expect(screen.getByText('Bundle summary')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'References' }));
    expect(screen.getByText('Reference One')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Runs' }));
    expect(screen.getByText('Run One')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Sources' }));
    expect(screen.getByText('Source One')).toBeInTheDocument();
  });
});

describe('thread bundle reference action', () => {
  it('preserves the reference endpoint and payload shape', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
    });
    vi.stubGlobal('fetch', fetchMock);

    await addThreadReference({
      apiUrl: 'http://api.test',
      workspaceId: 'workspace-1',
      threadId: 'thread-1',
      sourceType: 'url',
      uri: 'https://example.test/reference',
      title: 'Reference One',
      snippet: '',
      reason: 'Relevant',
    });

    expect(buildThreadReferenceUrl('http://api.test', 'workspace-1', 'thread-1')).toBe(
      'http://api.test/api/v1/workspaces/workspace-1/threads/thread-1/references',
    );
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/workspaces/workspace-1/threads/thread-1/references',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          source_type: 'url',
          uri: 'https://example.test/reference',
          title: 'Reference One',
          snippet: undefined,
          reason: 'Relevant',
        }),
      },
    );
  });

  it('surfaces backend detail on failed reference add', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'Reference rejected' }),
    }));

    await expect(addThreadReference({
      apiUrl: 'http://api.test',
      workspaceId: 'workspace-1',
      threadId: 'thread-1',
      sourceType: 'url',
      uri: 'https://example.test/reference',
      title: 'Reference One',
      snippet: '',
      reason: '',
    })).rejects.toThrow('Reference rejected');
  });
});

describe('thread bundle seam boundaries', () => {
  it('keeps touched files below the line gate', () => {
    const files = [
      'ThreadBundlePanel.tsx',
      'ThreadBundlePanel.spec.tsx',
      'threadBundlePanel/DeliverablesSection.tsx',
      'threadBundlePanel/EmptyBundleState.tsx',
      'threadBundlePanel/OverviewSection.tsx',
      'threadBundlePanel/ReferencePicker.tsx',
      'threadBundlePanel/ReferencesSection.tsx',
      'threadBundlePanel/RunsSection.tsx',
      'threadBundlePanel/SourcesSection.tsx',
      'threadBundlePanel/ThreadBundlePanelView.tsx',
      'threadBundlePanel/referenceActions.ts',
      'threadBundlePanel/sectionConfig.ts',
      'threadBundlePanel/types.ts',
    ];

    for (const file of files) {
      const lineCount = readFileSync(path.join(componentDir, file), 'utf8').split('\n').length;
      expect(lineCount, file).toBeLessThanOrEqual(500);
    }
  });

  it('keeps raw fetch ownership in the hook and reference action only', () => {
    const referenceActions = readFileSync(path.join(panelDir, 'referenceActions.ts'), 'utf8');
    expect(referenceActions).toContain('fetch(');
    expect(referenceActions).toContain('/api/v1/workspaces/${workspaceId}/threads/${threadId}/references');

    const passiveFiles = [
      'ThreadBundlePanel.tsx',
      'threadBundlePanel/DeliverablesSection.tsx',
      'threadBundlePanel/EmptyBundleState.tsx',
      'threadBundlePanel/OverviewSection.tsx',
      'threadBundlePanel/ReferencePicker.tsx',
      'threadBundlePanel/ReferencesSection.tsx',
      'threadBundlePanel/RunsSection.tsx',
      'threadBundlePanel/SourcesSection.tsx',
      'threadBundlePanel/ThreadBundlePanelView.tsx',
      'threadBundlePanel/sectionConfig.ts',
      'threadBundlePanel/types.ts',
    ];

    for (const file of passiveFiles) {
      const content = readFileSync(path.join(componentDir, file), 'utf8');
      expect(content, file).not.toMatch(
        /fetch\(|setInterval|setTimeout|AbortSignal|EventSource|WebSocket|worker|queue|pgbouncer|postgres|pool|poll|Promise\.all/,
      );
    }

    const hook = readFileSync(path.join(workspaceRoot, 'src/hooks/useThreadBundle.ts'), 'utf8');
    expect(hook).toContain('/api/v1/workspaces/${workspaceId}/threads/${threadId}/bundle');
  });

  it('preserves the global rail public import path', () => {
    const registration = readFileSync(
      path.join(workspaceRoot, 'src/app/workspaces/[workspaceId]/components/WorkspaceThreadBundleToolRegistration.tsx'),
      'utf8',
    );

    expect(registration).toContain("import('@/components/workspace/ThreadBundlePanel')");
    expect(registration).toContain("key: 'core:bundle'");
    expect(registration).toContain("useWorkspaceGlobalToolContributions('workspace-thread-bundle', contributions)");
  });
});
