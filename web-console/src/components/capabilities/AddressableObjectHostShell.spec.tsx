import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  AddressableObjectHostProvider,
  AddressableObjectHostShell,
  buildCapabilitySurfaceId,
} from './AddressableObjectHostShell';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

describe('AddressableObjectHostProvider', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    mockPush.mockReset();
    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const rawBody = typeof init?.body === 'string' ? init.body : '';
      if (url.includes('/api/v1/playbooks?')) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.includes('/api/v1/workspaces/ws-global/meeting-sessions?limit=')) {
        return new Response(
          JSON.stringify({
            sessions: [
              {
                id: 'mtg_existing',
                workspace_id: 'ws-global',
                started_at: '2026-04-27T03:00:00Z',
                is_active: true,
                status: 'active',
                meeting_type: 'workspace',
                agenda: ['Existing workspace meeting'],
                metadata: {},
              },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.includes('/selection/resolve')) {
        const isFoundationSelection = rawBody.includes('foundation_1');
        return new Response(
          JSON.stringify({
            workspace_id: 'ws-global',
            selection_id: 'sel_global',
            status: 'resolved',
            resolved_objects: [
              {
                ref: {
                  uri: isFoundationSelection
                    ? 'mindscape://public_persona_studio/foundation_snapshot/foundation_1'
                    : 'mindscape://ig/reference/ref_global',
                  owner_pack: isFoundationSelection ? 'public_persona_studio' : 'ig',
                  object_kind: isFoundationSelection ? 'foundation_snapshot' : 'reference',
                  object_id: isFoundationSelection ? 'foundation_1' : 'ref_global',
                },
                summary: {
                  ref: {
                    uri: isFoundationSelection
                      ? 'mindscape://public_persona_studio/foundation_snapshot/foundation_1'
                      : 'mindscape://ig/reference/ref_global',
                    owner_pack: isFoundationSelection ? 'public_persona_studio' : 'ig',
                    object_kind: isFoundationSelection ? 'foundation_snapshot' : 'reference',
                    object_id: isFoundationSelection ? 'foundation_1' : 'ref_global',
                  },
                  title: isFoundationSelection ? 'Foundation Snapshot' : 'Global Reference',
                  summary_text: isFoundationSelection
                    ? 'Shared host replacement'
                    : 'Shared host selection',
                  labels: [isFoundationSelection ? 'pps' : 'ig'],
                  owner_surface_url: isFoundationSelection
                    ? '/workspaces/ws-global/capabilities/public_persona_studio'
                    : '/workspaces/ws-global/capabilities/ig',
                },
                actions: [
                  {
                    action_code: 'attach_to_meeting',
                    label: 'Bring Into Meeting',
                    description: 'Attach object to meeting.',
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
            workspace_id: 'ws-global',
            meeting_id: 'mtg_global',
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

  it('mounts one shared anchor and one shared expansion surface across multiple shells', async () => {
    render(
      <AddressableObjectHostProvider workspaceId="ws-global">
        <AddressableObjectHostShell
          apiUrl="http://api.test"
          workspaceId="ws-global"
          capabilityCode="ig"
          route="/workspaces/ws-global/capabilities/ig"
          surfaceId={buildCapabilitySurfaceId('ig', 'IGWorkbenchPage')}
        >
          {(aolHost) => (
            <button
              type="button"
              data-testid="ig-select"
              onClick={() =>
                void aolHost.onSelectObject({
                  ownerPack: 'ig',
                  objectKind: 'reference',
                  objectId: 'ref_global',
                  sourceSurface: 'ig.references_grid',
                  label: 'Global Reference',
                })
              }
            >
              Select from IG
            </button>
          )}
        </AddressableObjectHostShell>
        <AddressableObjectHostShell
          apiUrl="http://api.test"
          workspaceId="ws-global"
          capabilityCode="public_persona_studio"
          route="/workspaces/ws-global/capabilities/public_persona_studio"
          surfaceId={buildCapabilitySurfaceId('public_persona_studio', 'PublicPersonaStudioPage')}
        >
          {(aolHost) => (
            <button
              type="button"
              data-testid="pps-select"
              onClick={() =>
                void aolHost.onSelectObject({
                  ownerPack: 'public_persona_studio',
                  objectKind: 'foundation_snapshot',
                  objectId: 'foundation_1',
                  sourceSurface: 'pps.overview',
                  label: 'Foundation Snapshot',
                })
              }
            >
              Select from PPS
            </button>
          )}
        </AddressableObjectHostShell>
      </AddressableObjectHostProvider>,
    );

    expect(await screen.findByTestId('aol-global-anchor')).not.toBeNull();
    expect(screen.getAllByTestId('aol-global-anchor')).toHaveLength(1);
    expect(screen.getByTestId('aol-object-tool-group')).not.toBeNull();
    expect(screen.getByTestId('aol-graph-shell-tool-group')).not.toBeNull();
    await waitFor(() => {
      expect(screen.getByTestId('aol-graph-shell-anchor')).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId('aol-global-anchor'));
    expect(await screen.findByText('Select an object on this page')).not.toBeNull();

    fireEvent.click(screen.getByTestId('ig-select'));
    expect(await screen.findByTestId('aol-host-panel')).not.toBeNull();
    expect(screen.getAllByTestId('aol-host-panel')).toHaveLength(1);
    expect(within(screen.getByTestId('aol-host-panel')).getAllByText('Global Reference')).toHaveLength(2);
    expect(screen.getByTestId('aol-graph-shell-anchor')).not.toBeDisabled();

    fireEvent.click(screen.getByTestId('aol-graph-shell-anchor'));
    await waitFor(() => {
      expect(screen.getByTestId('aol-meeting-pane')).not.toBeNull();
      expect(screen.getByTestId('aol-meeting-bottom-shell')).not.toBeNull();
      expect(screen.getByTestId('meeting-task-canvas')).not.toBeNull();
      expect(screen.queryByTestId('aol-host-panel')).toBeNull();
      expect(screen.getByTestId('aol-meeting-pane-compact')).not.toBeNull();
      expect(screen.getByTestId('aol-meeting-pane-default')).not.toBeNull();
      expect(screen.getByTestId('aol-meeting-pane-expanded')).not.toBeNull();
      expect(screen.getByTestId('aol-graph-shell-anchor')).toHaveAttribute('aria-pressed', 'true');
    });
    expect(screen.queryByTestId('aol-meeting-chat')).toBeNull();
    expect(screen.getByText('Ready for instruction')).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('opens the workspace graph shell from existing meeting sessions before object selection', async () => {
    render(
      <AddressableObjectHostProvider workspaceId="ws-global">
        <AddressableObjectHostShell
          apiUrl="http://api.test"
          workspaceId="ws-global"
          capabilityCode="ig"
          route="/workspaces/ws-global/capabilities/ig"
          surfaceId={buildCapabilitySurfaceId('ig', 'IGWorkbenchPage')}
        >
          {() => <div data-testid="ig-surface">IG surface</div>}
        </AddressableObjectHostShell>
      </AddressableObjectHostProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('aol-graph-shell-anchor')).not.toBeDisabled();
    });
    fireEvent.click(screen.getByTestId('aol-graph-shell-anchor'));

    expect(await screen.findByTestId('aol-meeting-pane')).toBeInTheDocument();
    fireEvent.click(await screen.findByTestId('meeting-sessions-toggle'));
    expect(await screen.findByTestId('meeting-session-card-mtg_existing')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('meeting-graph-node-root')).toHaveTextContent('mtg_existing');
    expect(screen.queryByTestId('aol-host-panel')).toBeNull();
  });

  it('can replace the selected object without spawning a second panel or leaving the page', async () => {
    render(
      <AddressableObjectHostProvider workspaceId="ws-global">
        <AddressableObjectHostShell
          apiUrl="http://api.test"
          workspaceId="ws-global"
          capabilityCode="ig"
          route="/workspaces/ws-global/capabilities/ig"
          surfaceId={buildCapabilitySurfaceId('ig', 'IGWorkbenchPage')}
        >
          {(aolHost) => (
            <button
              type="button"
              data-testid="ig-select"
              onClick={() =>
                void aolHost.onSelectObject({
                  ownerPack: 'ig',
                  objectKind: 'reference',
                  objectId: 'ref_global',
                  sourceSurface: 'ig.references_grid',
                  label: 'Global Reference',
                })
              }
            >
              Select from IG
            </button>
          )}
        </AddressableObjectHostShell>
        <AddressableObjectHostShell
          apiUrl="http://api.test"
          workspaceId="ws-global"
          capabilityCode="public_persona_studio"
          route="/workspaces/ws-global/capabilities/public_persona_studio"
          surfaceId={buildCapabilitySurfaceId('public_persona_studio', 'PublicPersonaStudioPage')}
        >
          {(aolHost) => (
            <button
              type="button"
              data-testid="pps-select"
              onClick={() =>
                void aolHost.onSelectObject({
                  ownerPack: 'public_persona_studio',
                  objectKind: 'foundation_snapshot',
                  objectId: 'foundation_1',
                  sourceSurface: 'pps.overview',
                  label: 'Foundation Snapshot',
                })
              }
            >
              Select from PPS
            </button>
          )}
        </AddressableObjectHostShell>
      </AddressableObjectHostProvider>,
    );

    fireEvent.click(await screen.findByTestId('aol-global-anchor'));
    fireEvent.click(screen.getByTestId('ig-select'));

    const panel = await screen.findByTestId('aol-host-panel');
    expect(screen.getAllByTestId('aol-host-panel')).toHaveLength(1);
    expect(within(panel).getAllByText('Global Reference')).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: 'Select Another Object' }));
    expect(await screen.findByText('Select an object on this page')).not.toBeNull();

    fireEvent.click(screen.getByTestId('pps-select'));
    await waitFor(() => {
      expect(screen.getAllByTestId('aol-host-panel')).toHaveLength(1);
      expect(within(screen.getByTestId('aol-host-panel')).getAllByText('Foundation Snapshot')).toHaveLength(2);
    });
    expect(mockPush).not.toHaveBeenCalled();
  });

  it('reuses the same shared expansion surface through selected, attaching, and meeting_opened states', async () => {
    let resolveAttachResponse: ((response: Response) => void) | null = null;
    const attachResponsePromise = new Promise<Response>((resolve) => {
      resolveAttachResponse = resolve;
    });

    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/selection/resolve')) {
        return new Response(
          JSON.stringify({
            workspace_id: 'ws-global',
            selection_id: 'sel_global',
            status: 'resolved',
            resolved_objects: [
              {
                ref: {
                  uri: 'mindscape://ig/reference/ref_global',
                  owner_pack: 'ig',
                  object_kind: 'reference',
                  object_id: 'ref_global',
                },
                summary: {
                  ref: {
                    uri: 'mindscape://ig/reference/ref_global',
                    owner_pack: 'ig',
                    object_kind: 'reference',
                    object_id: 'ref_global',
                  },
                  title: 'Global Reference',
                  summary_text: 'Shared host selection',
                  labels: ['ig'],
                },
                actions: [
                  {
                    action_code: 'attach_to_meeting',
                    label: 'Bring Into Meeting',
                    description: 'Attach object to meeting.',
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
        return attachResponsePromise;
      }

      return new Response(JSON.stringify({ detail: `Unhandled fetch ${url}` }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;

    render(
      <AddressableObjectHostProvider workspaceId="ws-global">
        <AddressableObjectHostShell
          apiUrl="http://api.test"
          workspaceId="ws-global"
          capabilityCode="ig"
          route="/workspaces/ws-global/capabilities/ig"
          surfaceId={buildCapabilitySurfaceId('ig', 'IGWorkbenchPage')}
        >
          {(aolHost) => (
            <button
              type="button"
              data-testid="ig-select"
              onClick={() =>
                void aolHost.onSelectObject({
                  ownerPack: 'ig',
                  objectKind: 'reference',
                  objectId: 'ref_global',
                  sourceSurface: 'ig.references_grid',
                  label: 'Global Reference',
                })
              }
            >
              Select from IG
            </button>
          )}
        </AddressableObjectHostShell>
      </AddressableObjectHostProvider>,
    );

    fireEvent.click(await screen.findByTestId('aol-global-anchor'));
    fireEvent.click(screen.getByTestId('ig-select'));

    const sharedPanel = await screen.findByTestId('aol-host-panel');
    expect(sharedPanel).toHaveAttribute('data-aol-mode', 'selected');
    expect(screen.getAllByTestId('aol-host-panel')).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Open Meeting' }));

    await waitFor(() => {
      expect(screen.getByTestId('aol-host-panel')).toBe(sharedPanel);
      expect(sharedPanel).toHaveAttribute('data-aol-mode', 'attaching');
      expect(screen.getAllByTestId('aol-host-panel')).toHaveLength(1);
      expect(screen.getByText('Opening meeting pane with object context...')).not.toBeNull();
    });

    expect(resolveAttachResponse).not.toBeNull();
    resolveAttachResponse!(
      new Response(
        JSON.stringify({
          workspace_id: 'ws-global',
          meeting_id: 'mtg_global',
          status: 'attached',
          attachments: [],
          staged_refs: [],
          review_routes: [],
          errors: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await waitFor(() => {
      expect(screen.queryByTestId('aol-host-panel')).toBeNull();
      expect(screen.getByTestId('aol-meeting-pane')).not.toBeNull();
      expect(screen.getByTestId('aol-meeting-bottom-shell')).not.toBeNull();
      expect(screen.queryByTestId('aol-meeting-chat')).toBeNull();
    });
    fireEvent.click(screen.getByTestId('meeting-object-context-toggle'));
    expect(await screen.findByTestId('meeting-object-context-panel')).not.toBeNull();
    expect(screen.getByTestId('meeting-object-context-panel')).toHaveTextContent('Global Reference');
    expect(mockPush).not.toHaveBeenCalled();
  });
});
