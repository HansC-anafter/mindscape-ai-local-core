import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  AOLRuntimeShell,
  AOLRuntimeShellProvider,
  buildCapabilitySurfaceId,
} from './index';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

describe('AOLRuntimeShell attach flow', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    mockPush.mockReset();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
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
      <AOLRuntimeShellProvider workspaceId="ws-global">
        <AOLRuntimeShell
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
        </AOLRuntimeShell>
      </AOLRuntimeShellProvider>,
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

  it('sends the selected generic context role when opening the meeting', async () => {
    const attachBodies: Array<Record<string, any>> = [];

    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const rawBody = typeof init?.body === 'string' ? init.body : '';

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
        const payload = JSON.parse(rawBody);
        attachBodies.push(payload);
        return new Response(
          JSON.stringify({
            workspace_id: 'ws-global',
            meeting_id: 'mtg_global',
            status: 'attached',
            attachments: payload.entries.map((entry: any) => ({
              role: entry.role,
              ref: entry.ref,
              projection_level: 'meeting',
            })),
            target_ref: payload.entries.find((entry: any) => entry.role === 'target')?.ref ?? null,
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

    render(
      <AOLRuntimeShellProvider workspaceId="ws-global">
        <AOLRuntimeShell
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
        </AOLRuntimeShell>
      </AOLRuntimeShellProvider>,
    );

    fireEvent.click(await screen.findByTestId('aol-global-anchor'));
    fireEvent.click(screen.getByTestId('ig-select'));
    expect(await screen.findByTestId('aol-role-control')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('aol-role-option-target'));
    fireEvent.click(screen.getByRole('button', { name: 'Open Meeting' }));

    await waitFor(() => {
      expect(attachBodies).toHaveLength(1);
    });
    expect(attachBodies[0].entries[0].role).toBe('target');
    expect(await screen.findByTestId('aol-meeting-pane')).toBeInTheDocument();
  });

  it('lets ambiguous selections be disambiguated before attaching with a selected role', async () => {
    const attachBodies: Array<Record<string, any>> = [];

    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const rawBody = typeof init?.body === 'string' ? init.body : '';
      const payload = rawBody ? JSON.parse(rawBody) : {};
      const objectId = payload?.hints?.object_id;

      if (url.includes('/selection/resolve') && objectId === 'ref_ambiguous') {
        return new Response(
          JSON.stringify({
            workspace_id: 'ws-global',
            selection_id: 'sel_global',
            status: 'ambiguous',
            resolved_objects: [],
            candidate_objects: [
              {
                ref: {
                  uri: 'mindscape://ig/reference/ref_a',
                  owner_pack: 'ig',
                  object_kind: 'reference',
                  object_id: 'ref_a',
                },
                summary: {
                  ref: {
                    uri: 'mindscape://ig/reference/ref_a',
                    owner_pack: 'ig',
                    object_kind: 'reference',
                    object_id: 'ref_a',
                  },
                  title: 'Reference A',
                  summary_text: 'First match',
                  labels: ['ig'],
                },
              },
              {
                ref: {
                  uri: 'mindscape://ig/reference/ref_b',
                  owner_pack: 'ig',
                  object_kind: 'reference',
                  object_id: 'ref_b',
                },
                summary: {
                  ref: {
                    uri: 'mindscape://ig/reference/ref_b',
                    owner_pack: 'ig',
                    object_kind: 'reference',
                    object_id: 'ref_b',
                  },
                  title: 'Reference B',
                  summary_text: 'Second match',
                  labels: ['ig'],
                },
              },
            ],
            errors: [],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.includes('/selection/resolve') && objectId === 'ref_b') {
        return new Response(
          JSON.stringify({
            workspace_id: 'ws-global',
            selection_id: 'sel_global',
            status: 'resolved',
            resolved_objects: [
              {
                ref: {
                  uri: 'mindscape://ig/reference/ref_b',
                  owner_pack: 'ig',
                  object_kind: 'reference',
                  object_id: 'ref_b',
                },
                summary: {
                  ref: {
                    uri: 'mindscape://ig/reference/ref_b',
                    owner_pack: 'ig',
                    object_kind: 'reference',
                    object_id: 'ref_b',
                  },
                  title: 'Reference B',
                  summary_text: 'Second match',
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
        attachBodies.push(payload);
        return new Response(
          JSON.stringify({
            workspace_id: 'ws-global',
            meeting_id: 'mtg_global',
            status: 'attached',
            attachments: payload.entries.map((entry: any) => ({
              role: entry.role,
              ref: entry.ref,
              projection_level: 'meeting',
            })),
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

    render(
      <AOLRuntimeShellProvider workspaceId="ws-global">
        <AOLRuntimeShell
          apiUrl="http://api.test"
          workspaceId="ws-global"
          capabilityCode="ig"
          route="/workspaces/ws-global/capabilities/ig"
          surfaceId={buildCapabilitySurfaceId('ig', 'IGWorkbenchPage')}
        >
          {(aolHost) => (
            <button
              type="button"
              data-testid="ig-select-ambiguous"
              onClick={() =>
                void aolHost.onSelectObject({
                  ownerPack: 'ig',
                  objectKind: 'reference',
                  objectId: 'ref_ambiguous',
                  sourceSurface: 'ig.references_grid',
                  label: 'Ambiguous Reference',
                })
              }
            >
              Select ambiguous ref
            </button>
          )}
        </AOLRuntimeShell>
      </AOLRuntimeShellProvider>,
    );

    fireEvent.click(await screen.findByTestId('aol-global-anchor'));
    fireEvent.click(screen.getByTestId('ig-select-ambiguous'));

    expect(await screen.findByTestId('aol-candidate-picker')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('aol-role-option-evidence'));
    fireEvent.click(screen.getByTestId('aol-candidate-ref_b'));

    await waitFor(() => {
      expect(within(screen.getByTestId('aol-host-panel')).getAllByText('Reference B').length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole('button', { name: 'Open Meeting' }));

    await waitFor(() => {
      expect(attachBodies).toHaveLength(1);
    });
    expect(attachBodies[0].entries[0].role).toBe('evidence');
    expect(attachBodies[0].entries[0].ref.object_id).toBe('ref_b');
  });
});
