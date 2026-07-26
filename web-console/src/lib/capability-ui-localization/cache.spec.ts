import { beforeEach, describe, expect, it } from 'vitest';

import {
  capabilityUiCatalogCacheStateForTests,
  clearCapabilityUiCatalogCacheForTests,
  loadCachedCapabilityUiCatalog,
} from './cache';
import type { LoadedCapabilityUiCatalog } from './contracts';

function pendingCatalog(): Promise<LoadedCapabilityUiCatalog> {
  return new Promise(() => undefined);
}

describe('capability UI localization cache', () => {
  beforeEach(() => {
    clearCapabilityUiCatalogCacheForTests();
  });

  it('bounds pending singleflight entries before any request resolves', async () => {
    for (let index = 0; index < 33; index += 1) {
      void loadCachedCapabilityUiCatalog(
        `pending-${index}`,
        pendingCatalog,
      );
    }
    await Promise.resolve();

    expect(capabilityUiCatalogCacheStateForTests()).toEqual({
      entries: 32,
      bytes: 0,
    });
  });
});
