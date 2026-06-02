import '@testing-library/jest-dom/vitest';
import React, { Suspense } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createRuntimeSettingsExtensionComponent,
  resolveRuntimeModalPanels,
  shouldRenderSettingsPanelInline,
} from './RuntimeEnvironmentsSettings';

const registryMock = vi.hoisted(() => ({
  loadRegisteredCapabilityComponentsContext: vi.fn(),
}));

vi.mock('../../../../lib/capability-ui-context-registry', () => ({
  loadRegisteredCapabilityComponentsContext: registryMock.loadRegisteredCapabilityComponentsContext,
}));

function LoadedRuntimePanel({ runtimeId }: { runtimeId?: string }) {
  return <div data-testid="loaded-runtime-panel">{runtimeId}</div>;
}

describe('RuntimeEnvironmentsSettings extension loader', () => {
  beforeEach(() => {
    registryMock.loadRegisteredCapabilityComponentsContext.mockReset();
  });

  it('loads runtime settings panels from the registered capability-scoped context', async () => {
    const context = Object.assign(
      vi.fn(async (key: string) => {
        if (key === './components/RuntimePanel.tsx') {
          return { default: LoadedRuntimePanel };
        }
        return { default: () => <div data-testid="unexpected-panel">{key}</div> };
      }),
      {
        keys: () => [
          './components/RuntimePanel.tsx',
          './components/SourcesTab.collections.cases.tsx',
        ],
      },
    );
    registryMock.loadRegisteredCapabilityComponentsContext.mockResolvedValue({
      capabilityCode: 'ig',
      context,
    });

    const LazyPanel = createRuntimeSettingsExtensionComponent({
      capabilityCode: 'ig',
      componentCode: 'RuntimePanel',
      title: 'Runtime Panel',
      importPath: '@/app/capabilities/ig/components/RuntimePanel.tsx',
      export: 'default',
    });

    render(
      <Suspense fallback={<div data-testid="runtime-panel-fallback">Loading</div>}>
        <LazyPanel runtimeId="ig-browser" />
      </Suspense>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loaded-runtime-panel')).toHaveTextContent('ig-browser');
    });
    expect(registryMock.loadRegisteredCapabilityComponentsContext).toHaveBeenCalledWith('ig');
    expect(context).toHaveBeenCalledWith('./components/RuntimePanel.tsx');
    expect(context).not.toHaveBeenCalledWith('./components/SourcesTab.collections.cases.tsx');
  });
});

describe('RuntimeEnvironmentsSettings panel placement', () => {
  it('places runtime-scoped settings and matching workflow panels in the runtime card modal', () => {
    const panels = [
      {
        capabilityCode: 'comfyui_runtime',
        componentCode: 'ComfyUIRuntimeSettingsPanel',
        section: 'runtime-environments' as const,
        title: 'ComfyUI Local Runtime',
        displayMode: 'runtime_modal',
        showWhen: {
          runtimeCodes: ['comfyui', 'comfyui_local', 'comfyui_runtime'],
        },
        importPath: '@/app/capabilities/comfyui_runtime/components/ComfyUIRuntimeSettingsPanel.tsx',
        export: 'default',
      },
      {
        capabilityCode: 'comfyui_runtime',
        componentCode: 'ComfyUIRuntimePanel',
        section: 'workflow-engines' as const,
        title: 'ComfyUI Runtime',
        importPath: '@/app/capabilities/comfyui_runtime/components/ComfyUIRuntimePanel.tsx',
        export: 'default',
      },
      {
        capabilityCode: 'unrelated_runtime',
        componentCode: 'OtherRuntimePanel',
        section: 'workflow-engines' as const,
        title: 'Other Runtime',
        importPath: '@/app/capabilities/other/components/OtherRuntimePanel.tsx',
        export: 'default',
      },
    ];

    const resolved = resolveRuntimeModalPanels(
      {
        id: 'comfyui-local',
        name: 'ComfyUI Local',
        description: 'Local ComfyUI runtime',
        icon: 'image',
        status: 'active',
      },
      panels,
    );

    expect(resolved.map((panel) => panel.componentCode)).toEqual([
      'ComfyUIRuntimeSettingsPanel',
      'ComfyUIRuntimePanel',
    ]);
  });

  it('keeps runtime-scoped panels out of the whole-page extension slot', () => {
    expect(shouldRenderSettingsPanelInline({
      capabilityCode: 'comfyui_runtime',
      componentCode: 'ComfyUIRuntimeSettingsPanel',
      title: 'ComfyUI Local Runtime',
      displayMode: 'runtime_modal',
      importPath: '@/app/capabilities/comfyui_runtime/components/ComfyUIRuntimeSettingsPanel.tsx',
      export: 'default',
    })).toBe(false);

    expect(shouldRenderSettingsPanelInline({
      capabilityCode: 'comfyui_runtime',
      componentCode: 'ComfyUIRuntimeSettingsPanel',
      title: 'ComfyUI Local Runtime',
      showWhen: {
        runtimeCodes: ['comfyui_runtime'],
      },
      importPath: '@/app/capabilities/comfyui_runtime/components/ComfyUIRuntimeSettingsPanel.tsx',
      export: 'default',
    })).toBe(false);

    expect(shouldRenderSettingsPanelInline({
      capabilityCode: 'global_capability',
      componentCode: 'GlobalSettingsPanel',
      title: 'Global Settings',
      importPath: '@/app/capabilities/global/components/GlobalSettingsPanel.tsx',
      export: 'default',
    })).toBe(true);
  });
});
