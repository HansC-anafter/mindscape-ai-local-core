import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import LegacyCapabilityUiHostRedirectPage from '@/app/capability-ui-hosts/[capabilityCode]/[workspaceId]/[[...surfacePath]]/page';
import PerformanceDirectionEntryPage from './page';
import PerformanceDirectionSessionPage from './sessions/[sessionId]/page';
import PerformanceDirectionStartPage from './start/page';

const mockRedirect = vi.fn();
const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  redirect: (...args: any[]) => mockRedirect(...args),
  usePathname: () => '/workspaces/ws_demo/capability-ui-hosts/performance_direction/start',
  useRouter: () => ({ push: mockPush }),
}));

describe('Performance Direction route split redirects', () => {
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
      '/workspaces/ws_demo/capability-ui-hosts/performance_direction/start',
    );
  });

  it('redirects legacy capability entry to a session-bound workbench route when a session query is present', () => {
    PerformanceDirectionEntryPage({
      params: { workspaceId: 'ws demo' },
      searchParams: { sessionId: 'ds session 001' },
    });

    expect(mockRedirect).toHaveBeenCalledWith(
      '/workspaces/ws%20demo/capability-ui-hosts/performance_direction/sessions/ds%20session%20001',
    );
  });

  it('redirects the legacy start route to the canonical workbench route', () => {
    PerformanceDirectionStartPage({ params: { workspaceId: 'ws_demo' } });

    expect(mockRedirect).toHaveBeenCalledWith(
      '/workspaces/ws_demo/capability-ui-hosts/performance_direction/start',
    );
  });

  it('redirects the legacy session route to the canonical workbench route', () => {
    PerformanceDirectionSessionPage({
      params: { workspaceId: 'ws_demo', sessionId: 'ds_route_001' },
    });

    expect(mockRedirect).toHaveBeenCalledWith(
      '/workspaces/ws_demo/capability-ui-hosts/performance_direction/sessions/ds_route_001',
    );
  });

  it('redirects the legacy top-level host shape to the canonical workbench route', () => {
    LegacyCapabilityUiHostRedirectPage({
      params: {
        capabilityCode: 'performance_direction',
        workspaceId: 'ws_demo',
        surfacePath: ['sessions', 'ds_route_001'],
      },
      searchParams: { component: 'PerformanceDirectionStoryboardEditorPage' },
    });

    expect(mockRedirect).toHaveBeenCalledWith(
      '/workspaces/ws_demo/capability-ui-hosts/performance_direction/sessions/ds_route_001?component=PerformanceDirectionStoryboardEditorPage',
    );
  });
});
