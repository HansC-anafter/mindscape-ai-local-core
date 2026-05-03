import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  AOLRuntimeShell,
  AOLRuntimeShellProvider,
  AddressableObjectPanel,
  AddressableObjectSourcePreview,
  RuntimeObjectPanel,
  RuntimeObjectSourcePreview,
  buildCapabilitySurfaceId,
} from './index';

describe('AOLRuntimeShellProvider', () => {
  it('exposes the new runtime shell names while preserving host behavior', () => {
    render(
      <AOLRuntimeShellProvider workspaceId="ws-global">
        <AOLRuntimeShell
          apiUrl="http://api.test"
          workspaceId="ws-global"
          capabilityCode="ig"
          route="/workspaces/ws-global/capabilities/ig"
          surfaceId={buildCapabilitySurfaceId('ig', 'IGWorkbenchPage')}
        >
          {(hostBridge) => (
            <button type="button" data-testid="runtime-shell-child">
              {hostBridge.mode}
            </button>
          )}
        </AOLRuntimeShell>
      </AOLRuntimeShellProvider>,
    );

    expect(screen.getByTestId('aol-global-anchor')).not.toBeNull();
    expect(screen.getByTestId('aol-shell-rail')).not.toBeNull();
    expect(screen.getByTestId('runtime-shell-child')).toHaveTextContent('idle');
    expect(buildCapabilitySurfaceId('ig', 'IGWorkbenchPage')).toBe(
      'capability_page:ig:IGWorkbenchPage',
    );
  });

  it('keeps runtime object exports available through legacy addressable aliases', () => {
    expect(AddressableObjectPanel).toBe(RuntimeObjectPanel);
    expect(AddressableObjectSourcePreview).toBe(RuntimeObjectSourcePreview);
  });
});
