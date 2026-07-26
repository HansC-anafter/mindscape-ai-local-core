import { act, render, screen } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({
    href,
    prefetch,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; prefetch?: boolean }) => (
    <a {...props} data-prefetch={String(prefetch)} href={href} />
  ),
}));

import RemoteWorkspaceLanding from './RemoteWorkspaceLanding';

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}

describe('bounded remote workspace landing', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('shows identity and projected capability links without full workspace controls', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/workspaces/workspace-a/summary')) {
        return jsonResponse({ id: 'workspace-a', name: 'Studio A', status: 'active' });
      }
      if (url.endsWith(
        '/api/v1/capability-packs/installed-capabilities?workspace_id=workspace-a',
      )) {
        return jsonResponse([
          { code: 'yogacoach', display_name: 'Yoga Coach' },
          { code: 'ig', display_name: 'Reference Library' },
        ]);
      }
      if (url.endsWith(
        '/api/v1/workspaces/workspace-a/product-configuration/effective',
      )) {
        return jsonResponse({
          source_runtime_id: 'runtime-a',
          workspace_id: 'workspace-a',
          workspace_scope_revision: 1,
          group_scope_revision: 0,
          workspace_admission_mode: 'configuration_only',
          available_products: [{
            pcs_id: 'guided_practice',
            exact_version: '1.0.0',
            display_name: 'Guided Practice',
            outcome_summary: 'Practice and teach back.',
            surface_ids: ['guided.practice'],
            closure_summary: {
              total_packs: 1,
              exact_ready_packs: 1,
              missing_packs: 0,
              disabled_packs: 0,
              version_mismatch_packs: 0,
            },
            pack_closure: [],
          }],
          effective_assignments: [{
            pcs_id: 'guided_practice',
            pcs_version: '1.0.0',
            product_surface_ids: ['guided.practice'],
            configuration_sources: ['workspace'],
            host_ready: true,
            host_admission: [],
          }],
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<RemoteWorkspaceLanding workspaceId="workspace-a" />);

    expect(await screen.findByRole('heading', { name: 'Studio A' })).toBeInTheDocument();
    expect(screen.getByText('Workspace ID: workspace-a')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Yoga Coach' })).toHaveAttribute(
      'href',
      '/workspaces/workspace-a/capability-ui-hosts/yogacoach',
    );
    expect(screen.getByRole('link', { name: 'Yoga Coach' })).toHaveAttribute(
      'data-prefetch',
      'false',
    );
    expect(screen.getByRole('link', { name: 'Reference Library' })).toHaveAttribute(
      'href',
      '/workspaces/workspace-a/capability-ui-hosts/ig',
    );
    expect(screen.getByTestId('remote-workspace-product-rail')).toHaveTextContent(
      'Guided Practice',
    );
    expect(screen.queryByText('Manage workspace products')).not.toBeInTheDocument();
    for (const control of [
      'Mindscape',
      'Graph',
      'System Settings',
      'Tasks',
      'Executions',
      'Health',
      'Projects',
      'Chat',
    ]) {
      expect(screen.queryByText(control, { exact: true })).not.toBeInTheDocument();
    }
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('starts three fixed requests including one WPCS read and adds no polling', async () => {
    vi.useFakeTimers();
    const intervalSpy = vi.spyOn(globalThis, 'setInterval');
    const fetchMock = vi.fn((_: RequestInfo | URL) => new Promise<Response>(() => {}));
    vi.stubGlobal('fetch', fetchMock);
    const { unmount } = render(<RemoteWorkspaceLanding workspaceId="workspace-a" />);

    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual([
      '/api/v1/workspaces/workspace-a/summary',
      '/api/v1/capability-packs/installed-capabilities?workspace_id=workspace-a',
      '/api/v1/workspaces/workspace-a/product-configuration/effective',
    ]);
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(intervalSpy).not.toHaveBeenCalled();
    unmount();
  });
});
