import { describe, expect, it } from 'vitest';

import { buildRuntimeAssetFetchUrl } from './capability-runtime-asset-url';

describe('buildRuntimeAssetFetchUrl', () => {
  it('uses integrity as the browser cache key', () => {
    expect(buildRuntimeAssetFetchUrl(
      '/api/v1/capability-packs/installed-capabilities/ig/ui-assets/1.0.106/components/IGWorkbenchPage.mjs',
      'sha256-PVBVUqVnf4EOnng0QA/xtyMYERq4hVddna0Zu/z2Iuk=',
    )).toBe(
      '/api/v1/capability-packs/installed-capabilities/ig/ui-assets/1.0.106/components/IGWorkbenchPage.mjs'
        + '?integrity=sha256-PVBVUqVnf4EOnng0QA%2FxtyMYERq4hVddna0Zu%2Fz2Iuk%3D',
    );
  });

  it('preserves existing query strings and hash fragments', () => {
    expect(buildRuntimeAssetFetchUrl(
      '/asset.mjs?pack=ig#runtime',
      'sha256-next',
    )).toBe('/asset.mjs?pack=ig&integrity=sha256-next#runtime');
  });

  it('adds explicit workspace context before the integrity cache key', () => {
    expect(buildRuntimeAssetFetchUrl(
      '/api/v1/capability-packs/installed-capabilities/ig/ui-assets/component.mjs',
      'sha256-next',
      'workspace-a',
    )).toBe(
      '/api/v1/capability-packs/installed-capabilities/ig/ui-assets/component.mjs'
        + '?workspace_id=workspace-a&integrity=sha256-next',
    );
  });

  it('does not change asset URLs without integrity', () => {
    expect(buildRuntimeAssetFetchUrl('/asset.mjs')).toBe('/asset.mjs');
  });
});
