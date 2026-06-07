import { describe, expect, it } from 'vitest';

import { buildApiRequestUrl } from './settingsApi';

describe('settingsApi request URL builder', () => {
  it('keeps relative API requests on the same-origin proxy in browsers', () => {
    expect(buildApiRequestUrl('', '/api/v1/system-settings/keyboard-shortcuts')).toBe(
      '/api/v1/system-settings/keyboard-shortcuts',
    );
  });

  it('rewrites Docker-internal backend URLs to same-origin paths in browsers', () => {
    expect(
      buildApiRequestUrl(
        'http://backend:8200',
        '/api/v1/tools/connections?profile_id=default-user',
      ),
    ).toBe('/api/v1/tools/connections?profile_id=default-user');
    expect(
      buildApiRequestUrl(
        '',
        'http://backend:8200/api/v1/tools/connections?profile_id=default-user',
      ),
    ).toBe('/api/v1/tools/connections?profile_id=default-user');
  });

  it('preserves externally reachable absolute URLs', () => {
    expect(
      buildApiRequestUrl(
        '',
        'https://api.example.com/api/v1/tools/connections?profile_id=default-user',
      ),
    ).toBe('https://api.example.com/api/v1/tools/connections?profile_id=default-user');
  });
});
