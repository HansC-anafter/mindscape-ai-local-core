import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { getInstalledCapabilities } from '@/lib/capability-packs/installed-capabilities-cache';
import { PackPanel } from './PackPanel';

const mockWindowOpen = vi.fn();

vi.mock('@/lib/i18n', () => ({
  useT: () => ((_: any) => null),
}));

vi.mock('@/components/workspace/ThinkingPanel', () => ({
  ThinkingPanel: () => <div>thinking-panel</div>,
}));

vi.mock('@/lib/capability-packs/installed-capabilities-cache', () => ({
  getInstalledCapabilities: vi.fn(),
}));

describe('PackPanel capability workbench routing', () => {
  beforeEach(() => {
    mockWindowOpen.mockReset();
    Object.defineProperty(window, 'open', {
      configurable: true,
      writable: true,
      value: mockWindowOpen,
    });

    vi.mocked(getInstalledCapabilities).mockResolvedValue([
        {
          id: 'mindscape_cloud_integration',
          code: 'mindscape_cloud_integration',
          display_name: 'Mindscape Cloud Integration',
          description: 'Gateway control plane',
          version: '1.0.0',
          ui_components: [
            {
              code: 'MindscapeMobileWorkbenchGatewayPage',
              path: 'ui/components/MindscapeMobileWorkbenchGatewayPage.tsx',
              description: 'Gateway policy page',
              export: 'default',
              artifact_types: [],
              playbook_codes: [],
              import_path: '@/app/capabilities/mindscape_cloud_integration/components/MindscapeMobileWorkbenchGatewayPage',
            },
          ],
        },
        {
          id: 'ig',
          code: 'ig',
          display_name: 'Instagram Workbench',
          description: 'IG capability',
          version: '1.0.0',
          ui_components: [
            {
              code: 'IGWorkbenchPage',
              path: 'ui/components/IGWorkbenchPage.tsx',
              description: 'IG workbench',
              export: 'default',
              artifact_types: [],
              playbook_codes: [],
              import_path: '@/app/capabilities/ig/components/IGWorkbenchPage',
            },
          ],
        },
      ]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('loads capabilities through the shared cache and opens the canonical workspace-scoped host route', async () => {
    render(
      <PackPanel
        workspaceId="ws-test"
        apiUrl="http://api.test"
      />,
    );

    await screen.findByText('Instagram Workbench');
    expect(getInstalledCapabilities).toHaveBeenCalledTimes(1);
    expect(getInstalledCapabilities).toHaveBeenCalledWith('http://api.test');
    fireEvent.click(screen.getAllByRole('button', { name: 'Open UI' })[1]);

    await waitFor(() => {
      expect(mockWindowOpen).toHaveBeenCalledWith(
        '/workspaces/ws-test/capability-ui-hosts/ig',
        '_blank',
      );
    });
  });

  it('opens the cloud integration gateway control page for the selected pack', async () => {
    render(
      <PackPanel
        workspaceId="ws-test"
        apiUrl="http://api.test"
      />,
    );

    await screen.findByText('Instagram Workbench');
    fireEvent.click(screen.getByRole('button', { name: 'Remote workbench' }));

    await waitFor(() => {
      expect(mockWindowOpen).toHaveBeenCalledWith(
        '/workspaces/ws-test/capability-ui-hosts/mindscape_cloud_integration?component=MindscapeMobileWorkbenchGatewayPage&target_capability=ig',
        '_blank',
      );
    });
  });
});
