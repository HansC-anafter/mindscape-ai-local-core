import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import PerformanceDirectionHostStartPage from '@/app/capability-ui-hosts/performance_direction/[workspaceId]/start/page';
import PerformanceDirectionHostSessionPage from '@/app/capability-ui-hosts/performance_direction/[workspaceId]/sessions/[sessionId]/page';
import PerformanceDirectionEntryPage from './page';
import PerformanceDirectionSessionPage from './sessions/[sessionId]/page';
import PerformanceDirectionStartPage from './start/page';

const mockRedirect = vi.fn();
const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  redirect: (...args: any[]) => mockRedirect(...args),
  usePathname: () => '/capability-ui-hosts/performance_direction/ws_demo/start',
  useRouter: () => ({ push: mockPush }),
}));

describe('Performance Direction route split host shell', () => {
  beforeEach(() => {
    mockRedirect.mockReset();
    mockPush.mockReset();
  });

  it('redirects legacy capability entry to the start surface when no session query is present', () => {
    PerformanceDirectionEntryPage({
      params: { workspaceId: 'ws_demo' },
      searchParams: {},
    });

    expect(mockRedirect).toHaveBeenCalledWith(
      '/capability-ui-hosts/performance_direction/ws_demo/start',
    );
  });

  it('redirects legacy capability entry to a session-bound workbench route when a session query is present', () => {
    PerformanceDirectionEntryPage({
      params: { workspaceId: 'ws demo' },
      searchParams: { sessionId: 'ds session 001' },
    });

    expect(mockRedirect).toHaveBeenCalledWith(
      '/capability-ui-hosts/performance_direction/ws%20demo/sessions/ds%20session%20001',
    );
  });

  it('redirects the legacy start route to the top-level host route', () => {
    PerformanceDirectionStartPage({ params: { workspaceId: 'ws_demo' } });

    expect(mockRedirect).toHaveBeenCalledWith(
      '/capability-ui-hosts/performance_direction/ws_demo/start',
    );
  });

  it('redirects the legacy session route to the top-level host route', () => {
    PerformanceDirectionSessionPage({
      params: { workspaceId: 'ws_demo', sessionId: 'ds_route_001' },
    });

    expect(mockRedirect).toHaveBeenCalledWith(
      '/capability-ui-hosts/performance_direction/ws_demo/sessions/ds_route_001',
    );
  });

  it('renders the top-level launcher route in explicit launcher mode', () => {
    render(<PerformanceDirectionHostStartPage params={{ workspaceId: 'ws_demo' }} />);

    expect(screen.getByTestId('pd-launcher-scroll-shell')).not.toBeNull();
    expect(screen.getByText('PD Start Surface')).not.toBeNull();
  });

  it('renders the top-level session route in explicit workbench mode', () => {
    render(
      <PerformanceDirectionHostSessionPage
        params={{ workspaceId: 'ws_demo', sessionId: 'ds_route_001' }}
      />,
    );

    expect(screen.getByTestId('capability-mainpage-scroll-shell')).not.toBeNull();
    expect(
      screen.getByTestId('aol-workspace-region').getAttribute('data-aol-active-surface'),
    ).toContain('PerformanceDirectionStoryboardEditorPage');
    expect(screen.getByText('Loading PD workbench...')).not.toBeNull();
  });
});
