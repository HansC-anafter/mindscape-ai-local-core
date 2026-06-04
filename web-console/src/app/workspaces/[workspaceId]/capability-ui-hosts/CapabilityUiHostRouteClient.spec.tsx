import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('./WorkspaceSurfaceShell', () => ({
  default: function MockWorkspaceSurfaceShell({
    workspaceId,
    activeCapabilityCode,
    surfacePath,
    children,
  }: {
    workspaceId: string;
    activeCapabilityCode: string;
    surfacePath?: readonly string[];
    children: React.ReactNode;
  }) {
    return (
      <div
        data-testid="route-shell"
        data-workspace-id={workspaceId}
        data-active-capability-code={activeCapabilityCode}
        data-surface-path={(surfacePath || []).join('/')}
      >
        {children}
      </div>
    );
  },
}));

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

async function flushRouteModuleImports() {
  await Promise.resolve();
  await Promise.resolve();
}

describe('CapabilityUiHostRouteClient', () => {
  it('keeps server render deterministic after route modules are cached', async () => {
    await flushRouteModuleImports();

    const html = renderToString(
      <CapabilityUiHostRouteClient
        workspaceId="ws_test"
        capabilityCode="ig"
        surfacePath={['accounts']}
      />,
    );

    expect(html).toContain('Loading capability UI...');
    expect(html).not.toContain('data-testid="route-shell"');
    expect(html).not.toContain('data-testid="route-loader"');
  });

  it('loads the workspace shell after the client effect resolves route modules', async () => {
    await flushRouteModuleImports();

    render(
      <CapabilityUiHostRouteClient
        workspaceId="ws_test"
        capabilityCode="ig"
        surfacePath={['accounts']}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('route-shell')).toHaveAttribute('data-active-capability-code', 'ig');
    });
    expect(screen.getByTestId('route-loader')).toHaveAttribute('data-surface-path', 'accounts');
  });
});
