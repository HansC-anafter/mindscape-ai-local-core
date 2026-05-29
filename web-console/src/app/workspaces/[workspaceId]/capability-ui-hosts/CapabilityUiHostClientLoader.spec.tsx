import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CapabilityUiHostClientLoader from './CapabilityUiHostClientLoader';

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/capability-static-hosts', () => ({
  buildCapabilityWorkbenchPath: (workspaceId: string, capabilityCode: string, options: { surfacePath?: readonly string[] }) => (
    `/workspaces/${workspaceId}/capability-ui-hosts/${capabilityCode}/${(options.surfacePath || []).join('/')}`
  ),
}));

vi.mock('../capabilities/[capabilityCode]/CapabilityLoadedComponents', () => ({
  default: function MockCapabilityLoadedComponents(props: {
    workspaceId: string;
    capabilityCode: string;
    capabilityInfo: { id?: string; code?: string };
    uiComponents: unknown[];
    aolRoutePath: string;
  }) {
    return (
      <div
        data-testid="loaded-capability-components"
        data-workspace-id={props.workspaceId}
        data-capability-code={props.capabilityCode}
        data-capability-id={props.capabilityInfo.id}
        data-ui-components={String(props.uiComponents.length)}
        data-aol-route-path={props.aolRoutePath}
      />
    );
  },
}));

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe('CapabilityUiHostClientLoader', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders a shell-local loading state before client-side metadata resolves', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_ok')) {
        return jsonResponse({ id: 'ig_loader_ok', code: 'ig_loader_ok' });
      }
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_ok/ui-components')) {
        return jsonResponse([{ code: 'IGWorkbenchPage' }]);
      }
      return jsonResponse({ detail: 'not found' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <CapabilityUiHostClientLoader
        workspaceId="ws_test"
        capabilityCode="ig_loader_ok"
        surfacePath={['accounts']}
      />,
    );

    expect(screen.getByText('Loading capability UI...')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('loaded-capability-components')).toHaveAttribute(
        'data-aol-route-path',
        '/workspaces/ws_test/capability-ui-hosts/ig_loader_ok/accounts',
      );
    });
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/capability-packs/installed-capabilities/ig_loader_ok',
      expect.objectContaining({ credentials: 'same-origin' }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/capability-packs/installed-capabilities/ig_loader_ok/ui-components',
      expect.objectContaining({ credentials: 'same-origin' }),
    );
  });

  it('falls back to capability id when code-based ui-components are empty', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_fallback')) {
        return jsonResponse({ id: 'capability_uuid', code: 'ig_loader_fallback' });
      }
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_fallback/ui-components')) {
        return jsonResponse([]);
      }
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/capability_uuid/ui-components')) {
        return jsonResponse([{ code: 'IGWorkbenchPage' }]);
      }
      return jsonResponse({ detail: 'not found' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <CapabilityUiHostClientLoader
        workspaceId="ws_test"
        capabilityCode="ig_loader_fallback"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loaded-capability-components')).toHaveAttribute(
        'data-capability-id',
        'capability_uuid',
      );
    });
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/capability-packs/installed-capabilities/capability_uuid/ui-components',
      expect.objectContaining({ credentials: 'same-origin' }),
    );
  });

  it('reloads metadata after remount instead of serving stale pack asset metadata', async () => {
    let components = [{ code: 'IGWorkbenchPage' }];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_refresh')) {
        return jsonResponse({ id: 'ig_loader_refresh', code: 'ig_loader_refresh' });
      }
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_refresh/ui-components')) {
        return jsonResponse(components);
      }
      return jsonResponse({ detail: 'not found' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    const firstRender = render(
      <CapabilityUiHostClientLoader
        workspaceId="ws_test"
        capabilityCode="ig_loader_refresh"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loaded-capability-components')).toHaveAttribute('data-ui-components', '1');
    });
    firstRender.unmount();

    components = [{ code: 'IGWorkbenchPage' }, { code: 'IGRunsWorkspaceToolPanel' }];
    render(
      <CapabilityUiHostClientLoader
        workspaceId="ws_test"
        capabilityCode="ig_loader_refresh"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loaded-capability-components')).toHaveAttribute('data-ui-components', '2');
    });
    expect(fetchMock.mock.calls.filter(([input]) => (
      String(input).endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_refresh/ui-components')
    ))).toHaveLength(2);
  });

  it('renders a recoverable error inside the shell when metadata loading fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'unavailable' }, 503)));

    render(
      <CapabilityUiHostClientLoader
        workspaceId="ws_test"
        capabilityCode="ig_loader_error"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Capability UI failed to load')).toBeInTheDocument();
      expect(screen.getByText('Request failed: 503')).toBeInTheDocument();
    });
  });
});
