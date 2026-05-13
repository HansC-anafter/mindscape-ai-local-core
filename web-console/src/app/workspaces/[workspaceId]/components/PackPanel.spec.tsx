import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { PackPanel } from './PackPanel';

const mockWindowOpen = vi.fn();

vi.mock('@/lib/i18n', () => ({
  useT: () => ((_: any) => null),
}));

vi.mock('@/components/workspace/ThinkingPanel', () => ({
  ThinkingPanel: () => <div>thinking-panel</div>,
}));

describe('PackPanel capability workbench routing', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    mockWindowOpen.mockReset();
    Object.defineProperty(window, 'open', {
      configurable: true,
      writable: true,
      value: mockWindowOpen,
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ([
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
      ]),
    } as Response);
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it('opens capability apps through the canonical workspace-scoped host route', async () => {
    render(
      <PackPanel
        workspaceId="ws-test"
        apiUrl="http://api.test"
      />,
    );

    await screen.findByText('Instagram Workbench');
    fireEvent.click(screen.getByRole('button', { name: 'Open UI' }));

    await waitFor(() => {
      expect(mockWindowOpen).toHaveBeenCalledWith(
        '/workspaces/ws-test/capability-ui-hosts/ig',
        '_blank',
      );
    });
  });
});
