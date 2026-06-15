import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import CapabilityLoadedComponentsView, {
  buildComponentKey,
  isMainPageComponent,
  type UIComponentInfo,
} from './CapabilityLoadedComponentsView';

vi.mock('next/navigation', () => ({
  usePathname: () => '/workspaces/ws_test/capability-ui-hosts/demo_capability',
  useRouter: () => ({
    back: vi.fn(),
    push: vi.fn(),
    replace: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/components/capabilities/aol-runtime-shell/AOLRuntimeShellBridge', () => ({
  AOLRuntimeShellBridge: ({
    children,
  }: {
    children: (host: Record<string, unknown>) => React.ReactNode;
  }) => (
    <div data-testid="aol-runtime-shell">{children({})}</div>
  ),
}));

function component(code: string): UIComponentInfo {
  return {
    code,
    path: `ui/components/${code}.tsx`,
    description: code,
    export: 'default',
    artifact_types: [],
    playbook_codes: [],
    import_path: `@/app/capabilities/example/components/${code}`,
  };
}

describe('CapabilityLoadedComponentsView', () => {
  it('treats workbench components as full-page capability entry points', () => {
    expect(isMainPageComponent(component('CreativeStudioWorkbench'))).toBe(true);
    expect(isMainPageComponent(component('CreativeStudioSeedSproutPlane'))).toBe(false);
    expect(isMainPageComponent(component('ReferenceGridCard'))).toBe(false);
  });

  it('renders a runtime-hosted main page without requiring an external AOL provider', () => {
    function DemoWorkbenchPage() {
      return <div data-testid="loaded-main-page">Demo workbench</div>;
    }

    render(
      <CapabilityLoadedComponentsView
        workspaceId="ws_test"
        capabilityCode="demo_capability"
        capabilityInfo={{ id: 'demo_capability', code: 'demo_capability', display_name: 'Demo Capability' }}
        uiComponents={[component('DemoWorkbenchPage')]}
        loadedComponents={new Map([
          [buildComponentKey('demo_capability', 'DemoWorkbenchPage'), DemoWorkbenchPage],
        ])}
        loading={false}
      />,
    );

    expect(screen.getByTestId('aol-runtime-shell')).toBeInTheDocument();
    expect(screen.getByTestId('loaded-main-page')).toHaveTextContent('Demo workbench');
  });
});
