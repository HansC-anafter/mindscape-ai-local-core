import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import SettingsPage from './page';

const navigationMock = vi.hoisted(() => ({
  push: vi.fn(),
  searchParams: new URLSearchParams('tab=remote_workbench_access'),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: navigationMock.push }),
  useSearchParams: () => navigationMock.searchParams,
}));

vi.mock('next/dynamic', async () => {
  const ReactModule = await import('react');
  return {
    default: (
      loader: () => Promise<React.ComponentType<Record<string, unknown>>>,
      options?: { loading?: React.ComponentType },
    ) => {
      const LazyComponent = ReactModule.lazy(async () => ({ default: await loader() }));
      return function TestDynamicComponent(props: Record<string, unknown>) {
        const fallback = options?.loading
          ? ReactModule.createElement(options.loading)
          : null;
        return ReactModule.createElement(
          ReactModule.Suspense,
          { fallback },
          ReactModule.createElement(LazyComponent, props),
        );
      };
    },
  };
});

vi.mock('../../components/Header', () => ({
  default: () => <div data-testid="settings-test-header" />,
}));

vi.mock('./hooks/useSettingsNotification', () => ({
  SettingsNotificationContainer: () => null,
  showNotification: vi.fn(),
}));

vi.mock('@/lib/api-url', () => ({ getApiBaseUrl: () => '' }));

describe('Remote Workbench Settings request budget', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    navigationMock.push.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('starts on the URL-selected tab and performs only one descriptor read over 60 seconds', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith('/api/v1/settings/extensions?')) {
        return {
          ok: true,
          status: 200,
          json: async () => [],
        } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<SettingsPage />);

    expect(await screen.findByTestId('remote-workbench-access-settings')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-config-assistant-column')).not.toBeInTheDocument();
    const currentNavigationButtons = screen.getAllByRole('button').filter(
      (button) => button.getAttribute('aria-current') === 'page',
    );
    expect(currentNavigationButtons).toHaveLength(2);
    currentNavigationButtons.forEach((button) => {
      expect(button).toHaveTextContent('Remote Workbench');
    });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/settings/extensions?section=remote-workbench-global-access&capability_code=mindscape_cloud_integration&component_code=MindscapeRemoteWorkbenchGlobalAdministratorsPanel',
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/health'))).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/config/backend'))).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/tools/connections'))).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/capability-packs/installed'))).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/capability-packs/enabled'))).toBe(false);
  });
});
