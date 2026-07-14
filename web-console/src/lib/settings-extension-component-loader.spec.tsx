import React, { Suspense } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createLazySettingsExtensionComponent } from './settings-extension-component-loader';

const capabilityLoaderMock = vi.hoisted(() => ({
  loadCapabilityUIComponent: vi.fn(),
  primeCapabilityUIComponentMetadata: vi.fn(),
}));

vi.mock('./capability-ui-loader', () => ({
  loadCapabilityUIComponent: capabilityLoaderMock.loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata: capabilityLoaderMock.primeCapabilityUIComponentMetadata,
}));

function LoadedSettingsExtension({ apiUrl }: { apiUrl: string }) {
  return <div data-testid="loaded-settings-extension">{apiUrl}</div>;
}

describe('settings extension component loader', () => {
  beforeEach(() => {
    capabilityLoaderMock.loadCapabilityUIComponent.mockResolvedValue(LoadedSettingsExtension);
    capabilityLoaderMock.primeCapabilityUIComponentMetadata.mockClear();
    capabilityLoaderMock.loadCapabilityUIComponent.mockClear();
  });

  it('does not poison the canonical metadata cache when runtime asset fields are absent', async () => {
    const LazyComponent = createLazySettingsExtensionComponent(
      {
        capability_code: 'blender_bridge',
        component_code: 'BlenderBridge3DMeshRuntimeSettingsPanel',
        description: '3D mesh runtime',
        export: 'default',
        import_path: '@/app/capabilities/blender_bridge/components/BlenderBridge3DMeshRuntimeSettingsPanel.tsx',
      },
      'http://api.test',
    );

    render(
      <Suspense fallback={<div data-testid="settings-loader-fallback">Loading</div>}>
        <LazyComponent apiUrl="http://api.test" />
      </Suspense>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loaded-settings-extension')).toHaveTextContent('http://api.test');
    });
    expect(capabilityLoaderMock.primeCapabilityUIComponentMetadata).not.toHaveBeenCalled();
    expect(capabilityLoaderMock.loadCapabilityUIComponent).toHaveBeenCalledWith(
      'blender_bridge',
      'BlenderBridge3DMeshRuntimeSettingsPanel',
      'http://api.test',
      undefined,
    );
  });

  it('primes exact runtime asset metadata and forwards workspace scope', async () => {
    const LazyComponent = createLazySettingsExtensionComponent(
      {
        capability_code: 'mindscape_cloud_integration',
        component_code: 'MindscapeRemoteWorkbenchWorkspaceAccessPanel',
        description: 'Workspace access',
        export: 'default',
        path: 'ui/components/MindscapeRemoteWorkbenchWorkspaceAccessPanel.tsx',
        import_path: '@/app/capabilities/mindscape_cloud_integration/components/MindscapeRemoteWorkbenchWorkspaceAccessPanel',
        asset_url: '/api/v1/capability-packs/installed-capabilities/mindscape_cloud_integration/ui-assets/1/panel.js',
        integrity: 'sha256-demo',
        runtime: 'mindscape-react-bridge-v1',
        bytes: 123,
      },
      'http://api.test',
      'ws-1',
    );

    render(
      <Suspense fallback={<div>Loading</div>}>
        <LazyComponent apiUrl="http://api.test" workspaceId="ws-1" />
      </Suspense>,
    );

    await waitFor(() => expect(screen.getByTestId('loaded-settings-extension')).toBeInTheDocument());
    expect(capabilityLoaderMock.primeCapabilityUIComponentMetadata).toHaveBeenCalledWith(
      'mindscape_cloud_integration',
      [expect.objectContaining({
        code: 'MindscapeRemoteWorkbenchWorkspaceAccessPanel',
        asset_url: '/api/v1/capability-packs/installed-capabilities/mindscape_cloud_integration/ui-assets/1/panel.js',
        integrity: 'sha256-demo',
        runtime: 'mindscape-react-bridge-v1',
        bytes: 123,
      })],
    );
    expect(capabilityLoaderMock.loadCapabilityUIComponent).toHaveBeenCalledWith(
      'mindscape_cloud_integration',
      'MindscapeRemoteWorkbenchWorkspaceAccessPanel',
      'http://api.test',
      'ws-1',
    );
  });

  it('renders an accessible failure instead of a silent null component', async () => {
    capabilityLoaderMock.loadCapabilityUIComponent.mockResolvedValueOnce(null);
    const LazyComponent = createLazySettingsExtensionComponent(
      {
        capability_code: 'mindscape_cloud_integration',
        component_code: 'MindscapeRemoteWorkbenchGlobalAdministratorsPanel',
        import_path: '@/app/capabilities/mindscape_cloud_integration/components/MindscapeRemoteWorkbenchGlobalAdministratorsPanel',
      },
      'http://api.test',
    );

    render(
      <Suspense fallback={<div role="status">Loading</div>}>
        <LazyComponent apiUrl="http://api.test" />
      </Suspense>,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unable to load settings extension mindscape_cloud_integration/MindscapeRemoteWorkbenchGlobalAdministratorsPanel.',
    );
  });
});
