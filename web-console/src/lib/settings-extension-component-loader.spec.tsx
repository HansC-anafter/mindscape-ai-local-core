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

  it('delegates settings panel loading to the capability UI loader without hardcoded component maps', async () => {
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
    expect(capabilityLoaderMock.primeCapabilityUIComponentMetadata).toHaveBeenCalledWith(
      'blender_bridge',
      [
        expect.objectContaining({
          code: 'BlenderBridge3DMeshRuntimeSettingsPanel',
          path: 'ui/components/BlenderBridge3DMeshRuntimeSettingsPanel.tsx',
          import_path: '@/app/capabilities/blender_bridge/components/BlenderBridge3DMeshRuntimeSettingsPanel.tsx',
        }),
      ],
    );
    expect(capabilityLoaderMock.loadCapabilityUIComponent).toHaveBeenCalledWith(
      'blender_bridge',
      'BlenderBridge3DMeshRuntimeSettingsPanel',
      'http://api.test',
    );
  });
});
