import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AOLRuntimeShellProvider } from '@/components/capabilities/aol-runtime-shell/AOLRuntimeShell';
import PerformanceDirectionLauncherHost from './PerformanceDirectionLauncherHost';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/capability-ui-hosts/performance_direction/ws_test/start',
  useRouter: () => ({
    push: mockPush,
  }),
}));

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://localhost:8220',
}));

vi.mock('@/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage', () => {
  throw new Error('PD launcher must not import the full storyboard editor');
});

describe('PerformanceDirectionLauncherHost', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    mockPush.mockReset();
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/capabilities/performance_direction/sessions?')) {
        return new Response(JSON.stringify({ sessions: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ detail: `Unhandled fetch ${url}` }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('renders the launcher without importing the full storyboard editor', async () => {
    render(
      <AOLRuntimeShellProvider workspaceId="ws_test">
        <PerformanceDirectionLauncherHost
          workspaceId="ws_test"
          sessionRouteBasePath="/capability-ui-hosts/performance_direction/ws_test/sessions"
        />
      </AOLRuntimeShellProvider>,
    );

    expect(await screen.findByText('PD Start Surface')).toBeInTheDocument();
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        'http://localhost:8220/api/v1/capabilities/performance_direction/sessions?workspace_id=ws_test&limit=8',
        { credentials: 'same-origin' },
      );
    });
  });

  it('opens the full editor only after a session is selected', async () => {
    render(
      <AOLRuntimeShellProvider workspaceId="ws_test">
        <PerformanceDirectionLauncherHost
          workspaceId="ws_test"
          sessionRouteBasePath="/capability-ui-hosts/performance_direction/ws_test/sessions"
        />
      </AOLRuntimeShellProvider>,
    );

    fireEvent.change(screen.getByLabelText('Direction session ID'), {
      target: { value: 'ds_test' },
    });
    fireEvent.click(screen.getByText('Load storyboard by session id'));

    expect(mockPush).toHaveBeenCalledWith(
      '/capability-ui-hosts/performance_direction/ws_test/sessions/ds_test',
    );
  });
});
