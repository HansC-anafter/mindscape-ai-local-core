import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderCapabilityUiHostPage } from './renderCapabilityUiHostPage';

vi.mock('./CapabilityUiHostRouteShell', () => ({
  default: function MockCapabilityUiHostRouteShell(props: {
    workspaceId: string;
    capabilityCode: string;
    surfacePath?: readonly string[];
  }) {
    return (
      <div
        data-testid="capability-ui-host-route-shell"
        data-workspace-id={props.workspaceId}
        data-capability-code={props.capabilityCode}
        data-surface-path={(props.surfacePath || []).join('/')}
      />
    );
  },
}));

describe('renderCapabilityUiHostPage', () => {
  it('renders the capability host inside a full-width non-shrinking viewport contract', () => {
    render(renderCapabilityUiHostPage({
      workspaceId: 'ws_demo',
      capabilityCode: 'ig',
      surfacePath: ['accounts'],
    }));

    expect(screen.getByTestId('capability-ui-host-viewport')).toHaveClass('w-full', 'min-w-0');
    expect(screen.getByTestId('capability-ui-host-frame')).toHaveClass('w-full', 'min-w-0', 'flex-1');
    expect(screen.getByTestId('capability-ui-host-main')).toHaveClass('w-full', 'min-w-0', 'flex-1');
    expect(screen.getByTestId('capability-ui-host-route-shell')).toHaveAttribute(
      'data-surface-path',
      'accounts',
    );
  });
});
