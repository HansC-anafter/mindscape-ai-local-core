import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RemoteWorkbenchAccessSettings } from './RemoteWorkbenchAccessSettings';

const slotMock = vi.hoisted(() => vi.fn());

vi.mock('@/components/capabilities/CapabilitySettingsExtensionSlot', () => ({
  default: (props: Record<string, unknown>) => {
    slotMock(props);
    return <div data-testid="global-access-slot">{String(props.section)}</div>;
  },
}));

describe('RemoteWorkbenchAccessSettings', () => {
  it('mounts only the dedicated global installed-pack section', () => {
    render(<RemoteWorkbenchAccessSettings />);

    expect(screen.getByRole('heading', { name: 'Remote Workbench Access' })).toBeInTheDocument();
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
