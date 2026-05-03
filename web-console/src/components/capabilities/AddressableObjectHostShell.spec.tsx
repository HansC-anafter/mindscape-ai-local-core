import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  AddressableObjectHostProvider,
  AddressableObjectHostShell,
  buildCapabilitySurfaceId,
} from './AddressableObjectHostShell';

describe('AddressableObjectHostShell compatibility facade', () => {
  it('keeps legacy exports wired to the AOL Runtime Shell implementation', () => {
    render(
      <AddressableObjectHostProvider workspaceId="ws-global">
        <AddressableObjectHostShell
          apiUrl="http://api.test"
          workspaceId="ws-global"
          capabilityCode="ig"
          route="/workspaces/ws-global/capabilities/ig"
          surfaceId={buildCapabilitySurfaceId('ig', 'IGWorkbenchPage')}
        >
          {(hostBridge) => (
            <button type="button" data-testid="legacy-shell-child">
              {hostBridge.mode}
            </button>
          )}
        </AddressableObjectHostShell>
      </AddressableObjectHostProvider>,
    );

    expect(screen.getByTestId('aol-global-anchor')).not.toBeNull();
    expect(screen.getByTestId('aol-shell-rail')).not.toBeNull();
    expect(screen.getByTestId('legacy-shell-child')).toHaveTextContent('idle');
    expect(buildCapabilitySurfaceId('ig', 'IGWorkbenchPage')).toBe(
      'capability_page:ig:IGWorkbenchPage',
    );
  });
});
