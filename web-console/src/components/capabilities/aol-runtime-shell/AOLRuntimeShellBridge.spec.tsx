import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AOLRuntimeShellBridge } from './AOLRuntimeShellBridge';

describe('AOLRuntimeShellBridge', () => {
  it('falls back to a no-op host when no provider is mounted', () => {
    render(
      <AOLRuntimeShellBridge
        apiUrl="http://api.test"
        workspaceId="ws_test"
        capabilityCode="demo_capability"
        route="/workspaces/ws_test/capability-ui-hosts/demo_capability"
        surfaceId="demo_capability:DemoWorkbenchPage"
      >
        {(host) => (
          <div data-testid="bridge-fallback-host">
            {host.mode}:{host.currentMeetingId === null ? 'no-meeting' : 'meeting'}
          </div>
        )}
      </AOLRuntimeShellBridge>,
    );

    expect(screen.getByTestId('bridge-fallback-host')).toHaveTextContent('idle:no-meeting');
  });
});
