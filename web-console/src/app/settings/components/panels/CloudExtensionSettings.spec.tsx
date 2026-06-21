import '@testing-library/jest-dom/vitest';
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CloudExtensionSettings } from './CloudExtensionSettings';

const notificationMock = vi.hoisted(() => ({
  showNotification: vi.fn(),
}));

vi.mock('../../hooks/useSettingsNotification', () => ({
  showNotification: notificationMock.showNotification,
}));

describe('CloudExtensionSettings install intake semantics', () => {
  beforeEach(() => {
    notificationMock.showNotification.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('queues install jobs without claiming completion or reloading packs immediately', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/v1/cloud-providers') {
        return {
          ok: true,
          json: async () => ([
            {
              provider_id: 'official',
              provider_type: 'official',
              enabled: true,
              configured: true,
              name: 'Official Cloud',
              description: 'Official provider',
              config: {
                api_url: 'https://cloud.example.test',
                license_key: 'masked',
              },
            },
          ]),
        } as Response;
      }

      if (url === '/api/v1/system-settings/cloud_frontend_url') {
        return {
          ok: true,
          json: async () => ({ value: 'https://cloud.example.test' }),
        } as Response;
      }

      if (url === '/api/v1/cloud-providers/official/packs') {
        return {
          ok: true,
          json: async () => ({
            packs: [
              {
                pack_ref: 'official:ig@1.0.0',
                code: 'ig',
                display_name: 'Instagram',
                version: '1.0.0',
                description: 'Instagram pack',
                bundle: 'default',
                size: 2048,
              },
            ],
          }),
        } as Response;
      }

      if (url === '/api/v1/capability-packs/') {
        return {
          ok: true,
          json: async () => ([]),
        } as Response;
      }

      if (url === '/api/v1/cloud-providers/official/install-default?bundle=default' && init?.method === 'POST') {
        return {
          ok: true,
          json: async () => ({
            success: true,
            accepted: true,
            bundle: 'default',
            provider_id: 'official',
            jobs: [
              {
                pack_code: 'ig',
                pack_ref: 'official:ig@1.0.0',
                install_id: 'job-1',
                state: 'queued',
                status_url: '/api/v1/capability-packs/install-jobs/job-1',
              },
            ],
            skipped: [],
          }),
        } as Response;
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<CloudExtensionSettings />);

    fireEvent.click(await screen.findByRole('button', { name: 'View Packs' }));

    await screen.findByText('Instagram');
    fireEvent.click(screen.getByRole('button', { name: 'Install All Packs' }));

    await waitFor(() => {
      expect(notificationMock.showNotification).toHaveBeenCalledWith(
        'success',
        'Queued 1 pack install job: ig. Check install job status for completion.',
      );
    });

    const providerPacksCalls = fetchMock.mock.calls.filter(([url]) => (
      String(url) === '/api/v1/cloud-providers/official/packs'
    ));
    expect(providerPacksCalls).toHaveLength(1);

    const successMessages = notificationMock.showNotification.mock.calls
      .filter(([kind]) => kind === 'success')
      .map(([, message]) => String(message));
    expect(successMessages.some((message) => message.startsWith('Installed'))).toBe(false);
  });
});
