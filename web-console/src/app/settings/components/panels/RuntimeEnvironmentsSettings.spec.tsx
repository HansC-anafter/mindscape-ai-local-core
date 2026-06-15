import '@testing-library/jest-dom/vitest';
import React, { Suspense } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createRuntimeSettingsExtensionComponent,
  resolveRuntimeModalPanels,
  RuntimeEnvironmentsSettings,
  shouldRenderSettingsPanelInline,
} from './RuntimeEnvironmentsSettings';

const registryMock = vi.hoisted(() => ({
  loadCapabilityUIComponent: vi.fn(),
  primeCapabilityUIComponentMetadata: vi.fn(),
}));

vi.mock('../../../../lib/capability-ui-loader', () => ({
  loadCapabilityUIComponent: registryMock.loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata: registryMock.primeCapabilityUIComponentMetadata,
}));

vi.mock('./HostResourcesPanel', () => ({
  HostResourcesPanel: () => <div data-testid="host-resources-panel" />,
}));

function LoadedRuntimePanel({ apiUrl, runtimeId }: { apiUrl?: string; runtimeId?: string }) {
  return <div data-testid="loaded-runtime-panel">{runtimeId || 'global'}:{apiUrl || 'no-api'}</div>;
}

describe('RuntimeEnvironmentsSettings extension loader', () => {
  beforeEach(() => {
    registryMock.loadCapabilityUIComponent.mockReset();
    registryMock.primeCapabilityUIComponentMetadata.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads runtime settings panels through the runtime asset-capable capability UI loader', async () => {
    registryMock.loadCapabilityUIComponent.mockResolvedValue(LoadedRuntimePanel);

    const LazyPanel = createRuntimeSettingsExtensionComponent({
      capabilityCode: 'global_runtime_status',
      componentCode: 'GlobalRuntimeStatusPanel',
      title: 'Global Runtime Status',
      description: 'Configure global runtime status',
      importPath: '@/app/capabilities/global_runtime_status/components/GlobalRuntimeStatusPanel.tsx',
      export: 'default',
    });

    render(
      <Suspense fallback={<div data-testid="runtime-panel-fallback">Loading</div>}>
        <LazyPanel runtimeId="ig-browser" />
      </Suspense>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('loaded-runtime-panel')).toHaveTextContent('ig-browser:');
    });
    expect(registryMock.primeCapabilityUIComponentMetadata).toHaveBeenCalledWith(
      'global_runtime_status',
      [
        expect.objectContaining({
          code: 'GlobalRuntimeStatusPanel',
          path: 'ui/components/GlobalRuntimeStatusPanel.tsx',
          import_path: '@/app/capabilities/global_runtime_status/components/GlobalRuntimeStatusPanel.tsx',
        }),
      ],
    );
    expect(registryMock.loadCapabilityUIComponent).toHaveBeenCalledWith(
      'global_runtime_status',
      'GlobalRuntimeStatusPanel',
      expect.any(String),
    );
  });

  it('renders pack-installed global runtime settings panels inline on the settings page', async () => {
    registryMock.loadCapabilityUIComponent.mockResolvedValue(LoadedRuntimePanel);
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes('/api/v1/runtime-environments')) {
        return {
          ok: true,
          json: async () => ({ runtimes: [] }),
        } as Response;
      }
      if (url.includes('/api/v1/settings/extensions?section=runtime-environments')) {
        return {
          ok: true,
          json: async () => ([{
            capability_code: 'global_runtime_status',
            component_code: 'GlobalRuntimeStatusPanel',
            section: 'runtime-environments',
            title: 'Global Runtime Status',
            description: 'Configure global runtime status.',
            display_mode: null,
            requires_workspace_id: false,
            show_when: { always: true },
            props_schema: null,
            import_path: '@/app/capabilities/global_runtime_status/components/GlobalRuntimeStatusPanel.tsx',
            export: 'default',
          }]),
        } as Response;
      }
      if (url.includes('/api/v1/settings/extensions?section=workflow-engines')) {
        return {
          ok: true,
          json: async () => ([]),
        } as Response;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<RuntimeEnvironmentsSettings />);

    await waitFor(() => {
      expect(screen.getByText('Global Runtime Status')).toBeInTheDocument();
      expect(screen.getByTestId('loaded-runtime-panel')).toHaveTextContent('global:');
    });
    expect(registryMock.loadCapabilityUIComponent).toHaveBeenCalledWith(
      'global_runtime_status',
      'GlobalRuntimeStatusPanel',
      expect.any(String),
    );
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
