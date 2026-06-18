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

vi.mock('./WorkspaceSurfaceShell', () => ({
  default: function MockWorkspaceSurfaceShell(props: {
    workspaceId: string;
    activeCapabilityCode: string;
    surfacePath?: readonly string[];
    children: React.ReactNode;
  }) {
    return (
      <div
        data-testid="workspace-surface-shell"
        data-workspace-id={props.workspaceId}
        data-active-capability-code={props.activeCapabilityCode}
        data-surface-path={(props.surfacePath || []).join('/')}
      >
        {props.children}
      </div>
    );
  },
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

  it('keeps bridge runtime capability hosts inside the workspace surface shell after metadata resolves', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_ok')) {
        return jsonResponse({ id: 'ig_loader_ok', code: 'ig_loader_ok' });
      }
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_ok/ui-components')) {
        return jsonResponse([{
          code: 'IGWorkbenchPage',
          asset_url: '/api/v1/capability-packs/installed-capabilities/ig_loader_ok/ui-assets/IGWorkbenchPage.mjs',
          runtime: 'mindscape-react-bridge-v1',
          layout_hint: 'scrollable_full_bleed',
        }]);
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
    expect(screen.getByTestId('workspace-surface-shell')).toHaveAttribute(
      'data-active-capability-code',
      'ig_loader_ok',
    );
    expect(screen.getByTestId('workspace-surface-shell')).toContainElement(
      screen.getByTestId('loaded-capability-components'),
    );
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
        return jsonResponse([{
          code: 'IGWorkbenchPage',
          asset_url: '/api/v1/capability-packs/installed-capabilities/capability_uuid/ui-assets/IGWorkbenchPage.mjs',
          runtime: 'mindscape-react-bridge-v1',
          layout_hint: 'scrollable_full_bleed',
        }]);
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

  it('wraps non-runtime capability hosts in the workspace surface shell', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/local_hosted_capability')) {
        return jsonResponse({ id: 'local_hosted_capability', code: 'local_hosted_capability' });
      }
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/local_hosted_capability/ui-components')) {
        return jsonResponse([
          {
            code: 'LocalHostedWorkbenchPage',
            runtime: null,
            asset_url: null,
            layout_hint: 'default',
          },
        ]);
      }
      return jsonResponse({ detail: 'not found' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <CapabilityUiHostClientLoader
        workspaceId="ws_test"
        capabilityCode="local_hosted_capability"
        surfacePath={['start']}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-surface-shell')).toHaveAttribute(
        'data-active-capability-code',
        'local_hosted_capability',
      );
    });
    expect(screen.getByTestId('loaded-capability-components')).toHaveAttribute(
      'data-aol-route-path',
      '/workspaces/ws_test/capability-ui-hosts/local_hosted_capability/start',
    );
    expect(screen.getByTestId('workspace-surface-shell')).toContainElement(
      screen.getByTestId('loaded-capability-components'),
    );
  });

  it('reuses fresh metadata after remount to avoid repeated pack asset metadata fetches', async () => {
    let now = 0;
    vi.spyOn(Date, 'now').mockImplementation(() => now);
    let components = [{
      code: 'IGWorkbenchPage',
      asset_url: '/api/v1/capability-packs/installed-capabilities/ig_loader_refresh/ui-assets/IGWorkbenchPage.mjs',
      runtime: 'mindscape-react-bridge-v1',
      layout_hint: 'scrollable_full_bleed',
    }];
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

    now = 1000;
    components = [{
      code: 'IGWorkbenchPage',
      asset_url: '/api/v1/capability-packs/installed-capabilities/ig_loader_refresh/ui-assets/IGWorkbenchPage.mjs',
      runtime: 'mindscape-react-bridge-v1',
      layout_hint: 'scrollable_full_bleed',
    }, {
      code: 'IGRunsWorkspaceToolPanel',
      asset_url: '/api/v1/capability-packs/installed-capabilities/ig_loader_refresh/ui-assets/IGRunsWorkspaceToolPanel.mjs',
      runtime: 'mindscape-react-bridge-v1',
      layout_hint: 'default',
    }];
    render(
      <CapabilityUiHostClientLoader
        workspaceId="ws_test"
        capabilityCode="ig_loader_refresh"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loaded-capability-components')).toHaveAttribute('data-ui-components', '1');
    });
    expect(fetchMock.mock.calls.filter(([input]) => (
      String(input).endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_refresh/ui-components')
    ))).toHaveLength(1);
  });

  it('revalidates stale metadata after remount so updated pack assets are visible in the same session', async () => {
    let now = 0;
    vi.spyOn(Date, 'now').mockImplementation(() => now);
    let components = [{
      code: 'IGWorkbenchPage',
      asset_url: '/api/v1/capability-packs/installed-capabilities/ig_loader_stale/ui-assets/IGWorkbenchPage.mjs',
      runtime: 'mindscape-react-bridge-v1',
      layout_hint: 'scrollable_full_bleed',
    }];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_stale')) {
        return jsonResponse({ id: 'ig_loader_stale', code: 'ig_loader_stale' });
      }
      if (url.endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_stale/ui-components')) {
        return jsonResponse(components);
      }
      return jsonResponse({ detail: 'not found' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    const firstRender = render(
      <CapabilityUiHostClientLoader
        workspaceId="ws_test"
        capabilityCode="ig_loader_stale"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loaded-capability-components')).toHaveAttribute('data-ui-components', '1');
    });
    firstRender.unmount();

    now = 3000;
    components = [{
      code: 'IGWorkbenchPage',
      asset_url: '/api/v1/capability-packs/installed-capabilities/ig_loader_stale/ui-assets/IGWorkbenchPage.mjs',
      runtime: 'mindscape-react-bridge-v1',
      layout_hint: 'scrollable_full_bleed',
    }, {
      code: 'IGRunsWorkspaceToolPanel',
      asset_url: '/api/v1/capability-packs/installed-capabilities/ig_loader_stale/ui-assets/IGRunsWorkspaceToolPanel.mjs',
      runtime: 'mindscape-react-bridge-v1',
      layout_hint: 'default',
    }];
    render(
      <CapabilityUiHostClientLoader
        workspaceId="ws_test"
        capabilityCode="ig_loader_stale"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loaded-capability-components')).toHaveAttribute('data-ui-components', '2');
    });
    expect(fetchMock.mock.calls.filter(([input]) => (
      String(input).endsWith('/api/v1/capability-packs/installed-capabilities/ig_loader_stale/ui-components')
    ))).toHaveLength(2);
  });

  it('renders a recoverable error inside the workspace surface shell when metadata loading fails', async () => {
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
    expect(screen.getByTestId('workspace-surface-shell')).toHaveAttribute(
      'data-active-capability-code',
      'ig_loader_error',
    );
    expect(screen.getByTestId('workspace-surface-shell')).toContainElement(
      screen.getByText('Capability UI failed to load'),
    );
  });

  it('renders a recoverable timeout error when metadata loading is aborted', async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error('signal is aborted without reason');
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <CapabilityUiHostClientLoader
        workspaceId="ws_test"
        capabilityCode="ig_loader_abort"
      />,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByText('Capability UI failed to load')).toBeInTheDocument();
    expect(screen.getByText('Capability UI metadata request timed out after 30 seconds')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-surface-shell')).toHaveAttribute(
      'data-active-capability-code',
      'ig_loader_abort',
    );
  });
});
