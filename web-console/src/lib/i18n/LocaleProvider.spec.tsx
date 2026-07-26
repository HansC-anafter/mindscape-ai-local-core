import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider, useLocaleContext, useT } from './index';

const refresh = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh }),
}));

function Consumer({ name }: { name: string }) {
  const { locale, setLocale, writable, error } = useLocaleContext();
  const t = useT();
  return (
    <div>
      <span data-testid={`${name}-locale`}>{locale}</span>
      <span data-testid={`${name}-message`}>{t('navSettings' as any)}</span>
      <span data-testid={`${name}-writable`}>{String(writable)}</span>
      {error && <span data-testid={`${name}-error`}>{error}</span>}
      {name === 'first' && (
        <button onClick={() => void setLocale('ja').catch(() => undefined)}>
          Japanese
        </button>
      )}
    </div>
  );
}

describe('LocaleProvider', () => {
  beforeEach(() => {
    refresh.mockReset();
    vi.restoreAllMocks();
  });

  it('updates all consumers after one account preference PATCH without reload', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        locale: 'ja',
        version: 4,
        source: 'profile',
      }),
    }) as Response);
    vi.stubGlobal('fetch', fetchMock);

    render(
      <LocaleProvider
        initialSnapshot={{
          locale: 'en',
          version: 3,
          source: 'profile',
          writable: true,
        }}
      >
        <Consumer name="first" />
        <Consumer name="second" />
      </LocaleProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Japanese' }));

    await waitFor(() => {
      expect(screen.getByTestId('first-locale')).toHaveTextContent('ja');
      expect(screen.getByTestId('second-locale')).toHaveTextContent('ja');
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/mindscape/profiles/me/preferences',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({
          preferred_ui_language: 'ja',
          expected_version: 3,
        }),
      }),
    );
    expect(document.documentElement.lang).toBe('ja');
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('keeps remote documents read-only and performs no browser preference request', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(
      <LocaleProvider
        initialSnapshot={{
          locale: 'zh-TW',
          version: 9,
          source: 'profile',
          writable: false,
        }}
      >
        <Consumer name="first" />
      </LocaleProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Japanese' }));

    await waitFor(() => {
      expect(screen.getByTestId('first-error')).toHaveTextContent(
        'read-only',
      );
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });
});
