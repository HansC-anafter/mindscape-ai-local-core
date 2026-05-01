import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import PerformanceDirectionWorkbenchHost from './PerformanceDirectionWorkbenchHost';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () =>
    '/workspaces/ws_test/capabilities/performance_direction/sessions/ds_ae738cc25079',
  useRouter: () => ({
    push: mockPush,
  }),
}));

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://localhost:8220',
}));

vi.mock('@/components/WorkspaceChat', () => ({
  default: function MockWorkspaceChat({
    threadId,
    layoutVariant,
  }: {
    threadId?: string | null;
    layoutVariant?: string;
  }) {
    return (
      <div data-testid="aol-meeting-chat">
        Meeting chat thread: {threadId || 'none'} | layout: {layoutVariant || 'default'}
      </div>
    );
  },
}));

vi.mock('@/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage', () => ({
  default: function MockPerformanceDirectionStoryboardEditorPage({
    aolHost,
  }: {
    aolHost: { onSelectObject: (selection: Record<string, unknown>) => void };
  }) {
    return (
      <button
        type="button"
        data-testid="pd-route-aol-trigger"
        onClick={() =>
          aolHost.onSelectObject({
            ownerPack: 'performance_direction',
            objectKind: 'storyboard_scene',
            objectId: 'ds_ae738cc25079:da_15a00efc56f6:sc01',
            label: 'sc01',
            role: 'target',
            selector: {
              session_id: 'ds_ae738cc25079',
              artifact_id: 'da_15a00efc56f6',
              scene_id: 'sc01',
            },
          })
        }
      >
        Select scene
      </button>
    );
  },
}));

describe('PerformanceDirectionWorkbenchHost AOL shell', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    mockPush.mockReset();
  });

  beforeEach(() => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/selection/resolve')) {
        return new Response(
          JSON.stringify({
            workspace_id: 'ws_test',
            selection_id: 'sel_test',
            status: 'resolved',
            resolved_objects: [
              {
                ref: {
                  uri: 'mindscape://performance_direction/storyboard_scene/ds_ae738cc25079:da_15a00efc56f6:sc01',
                  owner_pack: 'performance_direction',
                  object_kind: 'storyboard_scene',
                  object_id: 'ds_ae738cc25079:da_15a00efc56f6:sc01',
                },
                summary: {
                  ref: {
                    uri: 'mindscape://performance_direction/storyboard_scene/ds_ae738cc25079:da_15a00efc56f6:sc01',
                    owner_pack: 'performance_direction',
                    object_kind: 'storyboard_scene',
                    object_id: 'ds_ae738cc25079:da_15a00efc56f6:sc01',
                  },
                  title: 'sc01',
                  summary_text: 'Storyboard scene selection',
                  labels: ['storyboard_scene', 'performance_direction'],
                },
                actions: [
                  {
                    action_code: 'attach_to_meeting',
                    label: 'Bring Into Meeting',
                    description: 'Attach storyboard scene to a meeting.',
                    verb: 'attach',
                    mode: 'meeting',
                  },
                ],
              },
            ],
            candidate_objects: [],
            errors: [],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.includes('/object-meeting-attach')) {
        return new Response(
          JSON.stringify({
            workspace_id: 'ws_test',
            meeting_id: 'mtg_pd_route_test',
            status: 'attached',
            attachments: [],
            staged_refs: [],
            review_routes: [],
            errors: [],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
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

  it('wraps performance direction session routes with AOL host shell', async () => {
    render(
      <PerformanceDirectionWorkbenchHost
        workspaceId="ws_test"
        routeMode="workbench"
        routeSessionId="ds_ae738cc25079"
        sessionRouteBasePath="/workspaces/ws_test/capabilities/performance_direction/sessions"
      />,
    );

    expect(await screen.findByTestId('aol-global-anchor')).not.toBeNull();

    fireEvent.click(screen.getByTestId('pd-route-aol-trigger'));

    expect(await screen.findByTestId('aol-host-panel')).not.toBeNull();
    expect(screen.getByText('Open Meeting')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Open Meeting'));

    await waitFor(() => {
      expect(screen.getByTestId('aol-meeting-pane')).toBeInTheDocument();
      expect(screen.getByTestId('aol-meeting-bottom-shell')).toBeInTheDocument();
      expect(screen.queryByTestId('aol-host-panel')).toBeNull();
    });
    expect(screen.queryByTestId('aol-meeting-chat')).toBeNull();
    fireEvent.click(screen.getByTestId('meeting-object-context-toggle'));
    const objectContextPanel = await screen.findByTestId('meeting-object-context-panel');
    expect(within(objectContextPanel).getByText('sc01')).toBeInTheDocument();
    expect(within(objectContextPanel).getByText('mtg_pd_route_test')).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
