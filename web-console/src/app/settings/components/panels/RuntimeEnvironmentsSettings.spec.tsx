import React, { Suspense } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createRuntimeSettingsExtensionComponent } from './RuntimeEnvironmentsSettings';

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
