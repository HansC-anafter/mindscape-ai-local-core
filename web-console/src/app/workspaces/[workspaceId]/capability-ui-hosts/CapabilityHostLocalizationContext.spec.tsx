import { renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import type {
  CapabilityUiLocalizationBridgeV1,
} from '@/lib/capability-ui-localization';
import {
  CapabilityHostLocalizationProvider,
  useCapabilityHostLocalizationPromise,
} from './CapabilityHostLocalizationContext';

const bridge: CapabilityUiLocalizationBridgeV1 = {
  contract: 'mindscape-capability-ui-localization-bridge-v1',
  requestedLocale: 'zh-TW',
  effectiveLocale: 'zh-TW',
  direction: 'ltr',
  sourceLocale: 'en',
  status: 'ready',
  t: (key) => `translated:${key}`,
};
const localizationPromise = Promise.resolve(bridge);

describe('CapabilityHostLocalizationContext', () => {
  it('exposes the exact host-owned promise only to the matching capability', () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <CapabilityHostLocalizationProvider
        capabilityCode="ig"
        localizationPromise={localizationPromise}
      >
        {children}
      </CapabilityHostLocalizationProvider>
    );

    const matching = renderHook(
      () => useCapabilityHostLocalizationPromise('ig'),
      { wrapper },
    );
    const otherPack = renderHook(
      () => useCapabilityHostLocalizationPromise('web_generation'),
      { wrapper },
    );

    expect(matching.result.current).toBe(localizationPromise);
    expect(otherPack.result.current).toBeNull();
  });

  it('fails closed when no Host provider is mounted', () => {
    const { result } = renderHook(
      () => useCapabilityHostLocalizationPromise('ig'),
    );

    expect(result.current).toBeNull();
  });
});
