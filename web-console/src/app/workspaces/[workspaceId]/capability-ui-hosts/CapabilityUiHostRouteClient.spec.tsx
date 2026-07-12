import React from 'react';
import { render, screen } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('./CapabilityUiHostClientLoader', () => ({
  default: function MockCapabilityUiHostClientLoader({
    workspaceId,
    capabilityCode,
    surfacePath,
    remoteSurfaceMode,
  }: {
    workspaceId: string;
    capabilityCode: string;
    surfacePath?: readonly string[];
    remoteSurfaceMode?: boolean;
  }) {
    return (
      <div
        data-testid="route-loader"
        data-workspace-id={workspaceId}
        data-capability-code={capabilityCode}
        data-surface-path={(surfacePath || []).join('/')}
        data-remote-surface-mode={String(Boolean(remoteSurfaceMode))}
      />
    );
  },
}));

import CapabilityUiHostRouteClient from './CapabilityUiHostRouteClient';

describe('CapabilityUiHostRouteClient', () => {
  it('renders the bounded loading fallback while the lazy host loader resolves on the server', () => {
    const html = renderToString(
      <CapabilityUiHostRouteClient
        workspaceId="ws_test"
        capabilityCode="ig"
        surfacePath={['accounts']}
      />,
    );

    expect(html).toContain('Loading capability UI...');
  });

  it('renders the host loader with exact remote surface context on the client', async () => {
    render(
      <CapabilityUiHostRouteClient
        workspaceId="ws_test"
        capabilityCode="ig"
        surfacePath={['accounts']}
        remoteSurfaceMode
      />,
    );

    expect(await screen.findByTestId('route-loader')).toHaveAttribute('data-capability-code', 'ig');
    expect(screen.getByTestId('route-loader')).toHaveAttribute('data-surface-path', 'accounts');
    expect(screen.getByTestId('route-loader')).toHaveAttribute('data-remote-surface-mode', 'true');
  });
});
