import React from 'react';
import { render, screen } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('./CapabilityUiHostClientLoader', () => ({
  default: function MockCapabilityUiHostClientLoader({
    workspaceId,
    capabilityCode,
    surfacePath,
  }: {
    workspaceId: string;
    capabilityCode: string;
    surfacePath?: readonly string[];
  }) {
    return (
      <div
        data-testid="route-loader"
        data-workspace-id={workspaceId}
        data-capability-code={capabilityCode}
        data-surface-path={(surfacePath || []).join('/')}
      />
    );
  },
}));

import CapabilityUiHostRouteClient from './CapabilityUiHostRouteClient';

describe('CapabilityUiHostRouteClient', () => {
  it('renders the host loader during server render without waiting on route-local shell imports', () => {
    const html = renderToString(
      <CapabilityUiHostRouteClient
        workspaceId="ws_test"
        capabilityCode="ig"
        surfacePath={['accounts']}
      />,
    );

    expect(html).toContain('data-testid="route-loader"');
  });

  it('renders the host loader immediately on the client', () => {
    render(
      <CapabilityUiHostRouteClient
        workspaceId="ws_test"
        capabilityCode="ig"
        surfacePath={['accounts']}
      />,
    );

    expect(screen.getByTestId('route-loader')).toHaveAttribute('data-capability-code', 'ig');
    expect(screen.getByTestId('route-loader')).toHaveAttribute('data-surface-path', 'accounts');
  });
});
