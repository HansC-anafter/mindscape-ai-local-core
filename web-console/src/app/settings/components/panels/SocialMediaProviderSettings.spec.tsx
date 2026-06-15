import '@testing-library/jest-dom/vitest';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SocialMediaProviderSettings } from './SocialMediaProviderSettings';

const routerMock = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => routerMock,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('../../../../lib/settings-extension-component-loader', () => ({
  createLazySettingsExtensionComponent: () => function MockYoutubeSettingsPanel(props: { workspaceId?: string }) {
    return <div data-testid="mock-youtube-settings-panel">workspace:{props.workspaceId}</div>;
  },
}));

describe('SocialMediaProviderSettings workspace provider settings', () => {
  beforeEach(() => {
    routerMock.push.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders YouTube as a workspace-scoped pack settings panel instead of global OAuth', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/settings/extensions?section=social-media%3Ayoutube&workspace_id=ws_youtube')) {
        return {
          ok: true,
          json: async () => ([
            {
              capability_code: 'youtube',
              component_code: 'YoutubeRuntimeSettingsPanel',
              title: 'YouTube Data API',
              description: 'Configure workspace-scoped YouTube Data API key.',
              requires_workspace_id: true,
              import_path: '@/app/capabilities/youtube/components/YoutubeRuntimeSettingsPanel',
              export: 'default',
            },
          ]),
        } as Response;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <SocialMediaProviderSettings
        provider="youtube"
        workspaceId="ws_youtube"
        onBack={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mock-youtube-settings-panel')).toHaveTextContent('workspace:ws_youtube');
    });
    expect(screen.queryByText('OAuth Configuration')).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/v1/tools/connections'))).toBe(false);
  });
});
