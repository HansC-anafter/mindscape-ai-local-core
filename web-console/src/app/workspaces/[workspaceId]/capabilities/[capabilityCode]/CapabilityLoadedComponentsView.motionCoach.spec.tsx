import React from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CapabilityLoadedComponentsView, {
  buildComponentKey,
  type UIComponentInfo,
} from './CapabilityLoadedComponentsView';

const mockReplace = vi.fn();

const mocks = vi.hoisted(() => ({
  motionCoachHost: vi.fn((props: any) => (
    <div
      data-testid="motion-coach-host"
      data-capability-code={props.capabilityCode}
      data-workspace-id={props.workspaceId}
      data-api-url={props.apiUrl}
    >
      <props.Component
        workspaceId={props.workspaceId}
        apiUrl={props.apiUrl}
        aolHost={props.aolHost}
        surfacePath={props.surfacePath}
      />
    </div>
  )),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/workspaces/ws-test/capabilities/yogacoach',
  useRouter: () => ({
    back: vi.fn(),
    push: vi.fn(),
    replace: mockReplace,
  }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/components/capabilities/aol-runtime-shell/AOLRuntimeShellBridge', () => ({
  AOLRuntimeShellBridge: ({ children }: { children: (host: Record<string, unknown>) => React.ReactNode }) => (
    <div data-testid="aol-runtime-shell">{children({})}</div>
  ),
}));

vi.mock('./MotionCoachWorkbenchHost', () => ({
  default: (props: any) => mocks.motionCoachHost(props),
}));

function createUiComponent(code: string): UIComponentInfo {
  return {
    code,
    path: `ui/workbench/${code}.tsx`,
    description: `${code} description`,
    export: 'default',
    artifact_types: [],
    playbook_codes: [],
    import_path: `@/app/capabilities/demo/${code}`,
    layout_hint: 'scrollable_full_bleed',
  };
}

function createLoadedComponent(label: string) {
  return function LoadedComponent() {
    return <div data-testid={`loaded-component-${label}`}>{label}</div>;
  };
}

describe('CapabilityLoadedComponentsView motion coach host routing', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mocks.motionCoachHost.mockClear();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('routes YogaPracticeWorkbenchPage through MotionCoachWorkbenchHost', () => {
    const componentCode = 'YogaPracticeWorkbenchPage';
    const capabilityCode = 'yogacoach';
    const component = createUiComponent(componentCode);
    const LoadedComponent = createLoadedComponent('yoga');

    render(
      <CapabilityLoadedComponentsView
        workspaceId="ws-test"
        capabilityCode={capabilityCode}
        capabilityInfo={{ id: capabilityCode, code: capabilityCode, display_name: 'YogaCoach' }}
        uiComponents={[component]}
        loadedComponents={new Map([
          [buildComponentKey(capabilityCode, componentCode), LoadedComponent],
        ])}
        loading={false}
        surfacePath={['practice']}
      />,
    );

    expect(screen.getByTestId('motion-coach-host')).toHaveAttribute('data-capability-code', capabilityCode);
    expect(screen.getByTestId('loaded-component-yoga')).toBeTruthy();
    expect(mocks.motionCoachHost).toHaveBeenCalledTimes(1);
  });

  it('routes DancePracticeWorkbenchPage through MotionCoachWorkbenchHost', () => {
    const componentCode = 'DancePracticeWorkbenchPage';
    const capabilityCode = 'dance_motion_coach';
    const component = createUiComponent(componentCode);
    const LoadedComponent = createLoadedComponent('dance');

    render(
      <CapabilityLoadedComponentsView
        workspaceId="ws-test"
        capabilityCode={capabilityCode}
        capabilityInfo={{ id: capabilityCode, code: capabilityCode, display_name: 'Dance Motion Coach' }}
        uiComponents={[component]}
        loadedComponents={new Map([
          [buildComponentKey(capabilityCode, componentCode), LoadedComponent],
        ])}
        loading={false}
        surfacePath={['practice']}
      />,
    );

    expect(screen.getByTestId('motion-coach-host')).toHaveAttribute('data-capability-code', capabilityCode);
    expect(screen.getByTestId('loaded-component-dance')).toBeTruthy();
    expect(mocks.motionCoachHost).toHaveBeenCalledTimes(1);
  });

  it('keeps non-motion capabilities on the direct component path', () => {
    const capabilityCode = 'ig';
    const componentCode = 'IGWorkbenchPage';
    const LoadedComponent = createLoadedComponent('ig');

    render(
      <CapabilityLoadedComponentsView
        workspaceId="ws-test"
        capabilityCode={capabilityCode}
        capabilityInfo={{ id: capabilityCode, code: capabilityCode, display_name: 'Instagram' }}
        uiComponents={[createUiComponent(componentCode)]}
        loadedComponents={new Map([
          [buildComponentKey(capabilityCode, componentCode), LoadedComponent],
        ])}
        loading={false}
      />,
    );

    expect(screen.getByTestId('loaded-component-ig')).toBeTruthy();
    expect(screen.queryByTestId('motion-coach-host')).toBeNull();
    expect(mocks.motionCoachHost).not.toHaveBeenCalled();
  });
});
