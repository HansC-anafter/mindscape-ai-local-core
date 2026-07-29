import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RemoteWorkbenchAccessSettings } from './RemoteWorkbenchAccessSettings';

const slotMock = vi.hoisted(() => vi.fn());
const accessPanelMock = vi.hoisted(() => vi.fn());

vi.mock('@/components/access/AccessScopeManagementPanel', () => ({
  AccessScopeManagementPanel: (props: Record<string, unknown>) => {
    accessPanelMock(props);
    return <div data-testid="local-core-access-panel" />;
  },
}));

vi.mock('@/components/capabilities/CapabilitySettingsExtensionSlot', () => ({
  default: (props: Record<string, unknown>) => {
    slotMock(props);
    return <div data-testid="global-access-slot">{String(props.section)}</div>;
  },
}));

describe('RemoteWorkbenchAccessSettings', () => {
  it('mounts the host-owned account editor and pack-owned diagnostics slot', () => {
    render(<RemoteWorkbenchAccessSettings />);

    expect(screen.getByRole('heading', { name: 'Accounts & access' })).toBeInTheDocument();
    expect(screen.getByTestId('local-core-access-panel')).toBeInTheDocument();
    expect(accessPanelMock).toHaveBeenCalledWith(expect.objectContaining({
      endpoint: '/api/v1/access-control/local-core',
      scopeType: 'local_core',
    }));
    expect(screen.getByTestId('global-access-slot')).toHaveTextContent(
      'remote-workbench-global-access',
    );
    expect(slotMock).toHaveBeenCalledWith(expect.objectContaining({
      section: 'remote-workbench-global-access',
      ownerContract: {
        capabilityCode: 'mindscape_cloud_integration',
        componentCode: 'MindscapeRemoteWorkbenchGlobalAdministratorsPanel',
      },
    }));
    expect(slotMock.mock.calls[0][0]).not.toHaveProperty('workspaceId');
  });
});
