import { render, renderHook, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import {
  CapabilityMessage,
  CapabilityUiLocalizationProvider,
  createLocalizedCapabilityEntry,
  type CapabilityUiLocalizationBridgeV1,
  useCapabilityLocalization,
  useOptionalCapabilityLocalization,
} from '@/lib/capability-ui-localization';

const bridge: CapabilityUiLocalizationBridgeV1 = {
  contract: 'mindscape-capability-ui-localization-bridge-v1',
  requestedLocale: 'ja',
  effectiveLocale: 'en',
  direction: 'ltr',
  sourceLocale: 'en',
  status: 'source-fallback',
  t: (key, values) => (
    key === 'runtime.greeting'
      ? `Hello ${String(values?.name)}`
      : `translated:${key}`
  ),
};

describe('capability UI localization runtime facade', () => {
  it('returns null from the optional hook outside a localized capability entry', () => {
    const { result } = renderHook(() => useOptionalCapabilityLocalization());

    expect(result.current).toBeNull();
  });

  it('exposes exactly the host-owned bridge to descendants', () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <CapabilityUiLocalizationProvider localization={bridge}>
        {children}
      </CapabilityUiLocalizationProvider>
    );

    const { result } = renderHook(
      () => useCapabilityLocalization(),
      { wrapper },
    );

    expect(result.current).toBe(bridge);
    expect(result.current.t('runtime.loading')).toBe(
      'translated:runtime.loading',
    );
  });

  it('exposes the requested locale through the optional cross-bundle context', () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <CapabilityUiLocalizationProvider localization={bridge}>
        {children}
      </CapabilityUiLocalizationProvider>
    );

    const { result } = renderHook(
      () => useOptionalCapabilityLocalization(),
      { wrapper },
    );

    expect(result.current?.requestedLocale).toBe('ja');
  });

  it('renders messages through the provided bridge', () => {
    render(
      <CapabilityUiLocalizationProvider localization={bridge}>
        <CapabilityMessage
          id="runtime.greeting"
          values={{ name: 'Momo' }}
        />
      </CapabilityUiLocalizationProvider>,
    );

    expect(screen.getByText('Hello Momo')).toBeInTheDocument();
  });

  it('mounts a domain component through the single localized entry seam', () => {
    function DomainComponent({ label }: { label: string }) {
      const localization = useCapabilityLocalization();
      return (
        <div>
          {label}:{localization.t('runtime.loading')}
        </div>
      );
    }
    const LocalizedEntry = createLocalizedCapabilityEntry(DomainComponent);

    render(<LocalizedEntry label="domain" localization={bridge} />);

    expect(screen.getByText('domain:translated:runtime.loading')).toBeInTheDocument();
  });

  it('refuses to mount a localized Pack without the host bridge', () => {
    function DomainComponent() {
      return <div>domain</div>;
    }
    const LocalizedEntry = createLocalizedCapabilityEntry(DomainComponent);

    expect(() => render(<LocalizedEntry />)).toThrow(
      'Capability UI localization bridge is unavailable',
    );
  });
});
