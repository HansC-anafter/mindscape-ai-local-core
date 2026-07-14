import '@testing-library/jest-dom/vitest';
import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CapabilitySettingsExtensionSlot from './CapabilitySettingsExtensionSlot';

const loaderMock = vi.hoisted(() => ({ create: vi.fn() }));
const globalOwner = {
  capabilityCode: 'mindscape_cloud_integration',
  componentCode: 'MindscapeRemoteWorkbenchGlobalAdministratorsPanel',
};
const workspaceOwner = {
  capabilityCode: 'mindscape_cloud_integration',
  componentCode: 'MindscapeRemoteWorkbenchWorkspaceAccessPanel',
};

vi.mock('@/lib/api-url', () => ({ getApiBaseUrl: () => 'http://api.test' }));
vi.mock('@/lib/settings-extension-component-loader', () => ({
  createLazySettingsExtensionComponent: (...args: unknown[]) => loaderMock.create(...args),
}));

function LoadedPanel({ workspaceId }: { workspaceId?: string }) {
  return <div data-testid="loaded-extension-panel">{workspaceId || 'global'}</div>;
}

function descriptor(
  componentCode: string,
  requiresWorkspaceId: boolean,
  capabilityCode = 'mindscape_cloud_integration',
) {
  return {
    capability_code: capabilityCode,
    component_code: componentCode,
    title: componentCode,
    description: 'Remote Workbench access',
    requires_workspace_id: requiresWorkspaceId,
    import_path: `@/app/capabilities/mindscape_cloud_integration/components/${componentCode}`,
    export: 'default',
  };
}

describe('CapabilitySettingsExtensionSlot', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    loaderMock.create.mockReset();
    loaderMock.create.mockReturnValue(LoadedPanel);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('loads one workspace descriptor request, excludes global panels, and never polls', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: async () => [descriptor('MindscapeRemoteWorkbenchWorkspaceAccessPanel', true)],
    }) as Response);
    vi.stubGlobal('fetch', fetchMock);

    render(
      <CapabilitySettingsExtensionSlot
        section="remote-workbench-workspace-access"
        workspaceId="ws-1"
        workspaceScopedOnly
        ownerContract={workspaceOwner}
      />,
    );

    expect(await screen.findByTestId('loaded-extension-panel')).toHaveTextContent('ws-1');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://api.test/api/v1/settings/extensions?section=remote-workbench-workspace-access&workspace_id=ws-1&capability_code=mindscape_cloud_integration&component_code=MindscapeRemoteWorkbenchWorkspaceAccessPanel',
    );
    expect(loaderMock.create).toHaveBeenCalledTimes(1);
    expect(loaderMock.create).toHaveBeenCalledWith(
      expect.objectContaining({ component_code: 'MindscapeRemoteWorkbenchWorkspaceAccessPanel' }),
      'http://api.test',
      'ws-1',
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('ignores an old workspace response that completes after the new workspace response', async () => {
    const jsonResolvers: Array<(payload: unknown) => void> = [];
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: () => new Promise((resolve) => jsonResolvers.push(resolve)),
    }) as Response);
    vi.stubGlobal('fetch', fetchMock);

    const { rerender } = render(
      <CapabilitySettingsExtensionSlot
        section="remote-workbench-workspace-access"
        workspaceId="ws-1"
        workspaceScopedOnly
        ownerContract={workspaceOwner}
      />,
    );
    await waitFor(() => expect(jsonResolvers).toHaveLength(1));

    rerender(
      <CapabilitySettingsExtensionSlot
        section="remote-workbench-workspace-access"
        workspaceId="ws-2"
        workspaceScopedOnly
        ownerContract={workspaceOwner}
      />,
    );
    await waitFor(() => expect(jsonResolvers).toHaveLength(2));
    expect(String(fetchMock.mock.calls[1][0])).toContain('workspace_id=ws-2');

    await act(async () => {
      jsonResolvers[1]([descriptor('MindscapeRemoteWorkbenchWorkspaceAccessPanel', true)]);
      await Promise.resolve();
    });
    expect(await screen.findByTestId('loaded-extension-panel')).toHaveTextContent('ws-2');

    await act(async () => {
      jsonResolvers[0]([descriptor('MindscapeRemoteWorkbenchWorkspaceAccessPanel', true)]);
      await Promise.resolve();
    });
    expect(screen.getByTestId('loaded-extension-panel')).toHaveTextContent('ws-2');
    expect(loaderMock.create).toHaveBeenCalledTimes(1);
  });

  it('mounts the global section without a workspace identifier', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: async () => [descriptor('MindscapeRemoteWorkbenchGlobalAdministratorsPanel', false)],
    }) as Response);
    vi.stubGlobal('fetch', fetchMock);

    render(
      <CapabilitySettingsExtensionSlot
        section="remote-workbench-global-access"
        ownerContract={globalOwner}
      />,
    );

    expect(await screen.findByTestId('loaded-extension-panel')).toHaveTextContent('global');
    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://api.test/api/v1/settings/extensions?section=remote-workbench-global-access&capability_code=mindscape_cloud_integration&component_code=MindscapeRemoteWorkbenchGlobalAdministratorsPanel',
    );
  });

  it('preserves the generic endpoint shape when no owner contract is supplied', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [descriptor('GenericWorkspacePanel', true, 'generic_pack')],
    }) as Response);
    vi.stubGlobal('fetch', fetchMock);

    render(
      <CapabilitySettingsExtensionSlot
        section="runtime-environments"
        workspaceId="ws-1"
        workspaceScopedOnly
      />,
    );

    expect(await screen.findByTestId('loaded-extension-panel')).toHaveTextContent('ws-1');
    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://api.test/api/v1/settings/extensions?section=runtime-environments&workspace_id=ws-1',
    );
  });

  it('aborts the owner-scoped request on unmount without retrying', async () => {
    let requestSignal: AbortSignal | undefined;
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      requestSignal = init?.signal || undefined;
      return new Promise<Response>(() => undefined);
    });
    vi.stubGlobal('fetch', fetchMock);

    const { unmount } = render(
      <CapabilitySettingsExtensionSlot
        section="remote-workbench-global-access"
        ownerContract={globalOwner}
      />,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    unmount();

    expect(requestSignal?.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('times out an owner-scoped request after ten seconds without retrying', async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => (
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('aborted', 'AbortError'));
        });
      })
    ));
    vi.stubGlobal('fetch', fetchMock);

    render(
      <CapabilitySettingsExtensionSlot
        section="remote-workbench-global-access"
        ownerContract={globalOwner}
      />,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('request timed out');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('fails closed with the configured empty state when the exact owner is absent', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [],
    }) as Response));

    render(
      <CapabilitySettingsExtensionSlot
        section="remote-workbench-global-access"
        ownerContract={globalOwner}
        emptyMessage="Required extension unavailable"
      />,
    );

    expect(await screen.findByText('Required extension unavailable')).toBeInTheDocument();
    expect(loaderMock.create).not.toHaveBeenCalled();
  });

  it.each([
    {
      name: 'wrong component owner',
      payload: [descriptor('WrongGlobalPanel', false)],
    },
    {
      name: 'wrong capability owner',
      payload: [descriptor('MindscapeRemoteWorkbenchGlobalAdministratorsPanel', false, 'another_pack')],
    },
    {
      name: 'multiple exact owners',
      payload: [
        descriptor('MindscapeRemoteWorkbenchGlobalAdministratorsPanel', false),
        descriptor('MindscapeRemoteWorkbenchGlobalAdministratorsPanel', false),
      ],
    },
    {
      name: 'mixed expected and foreign owners',
      payload: [
        descriptor('MindscapeRemoteWorkbenchGlobalAdministratorsPanel', false),
        descriptor('ForeignGlobalPanel', false, 'another_pack'),
      ],
    },
  ])('fails closed for $name', async ({ payload }) => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => payload,
    }) as Response));

    render(
      <CapabilitySettingsExtensionSlot
        section="remote-workbench-global-access"
        ownerContract={globalOwner}
      />,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('owner contract mismatch');
    expect(loaderMock.create).not.toHaveBeenCalled();
  });
});
