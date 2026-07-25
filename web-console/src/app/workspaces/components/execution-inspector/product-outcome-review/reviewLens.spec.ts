import { describe, expect, it } from 'vitest';
import type { UIComponentInfo } from '@/lib/capability-ui-loader';
import { selectPinnedReviewLensComponent } from './reviewLens';
import type { ReviewLensPin } from './types';

const integrity = 'sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=';

function pin(capabilityCode: string): ReviewLensPin {
  return {
    capability_code: capabilityCode,
    pack_version: '1.0.0',
    manifest_sha256: '0'.repeat(64),
    descriptor_sha256: '1'.repeat(64),
    component_code: 'ProductOutcomeReviewLens',
    integrity,
    runtime: 'esm',
    export: 'default',
  };
}

function component(overrides: Partial<UIComponentInfo> = {}): UIComponentInfo {
  return {
    code: 'ProductOutcomeReviewLens',
    path: 'ui/outcome/ProductOutcomeReviewLens.tsx',
    description: 'Optional product outcome labels',
    export: 'default',
    artifact_types: [],
    playbook_codes: [],
    import_path: 'ignored-by-runtime-lens',
    asset_url: '/api/v1/capability-ui/runtime/review-lens.mjs',
    integrity,
    runtime: 'esm',
    ...overrides,
  };
}

describe('neutral product outcome review lens selection', () => {
  it.each(['alpha_capability', 'beta_capability'])(
    'accepts the exact runtime pin for %s',
    (capabilityCode) => {
      const selected = selectPinnedReviewLensComponent(
        [component()],
        pin(capabilityCode),
      );
      expect(selected?.pin.capability_code).toBe(capabilityCode);
      expect(selected?.component.asset_url).toContain('.mjs');
    },
  );

  it('fails closed on mismatch, ambiguity, or legacy-only metadata', () => {
    const exactPin = pin('gamma_capability');
    expect(selectPinnedReviewLensComponent(
      [component({ integrity: 'sha256-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=' })],
      exactPin,
    )).toBeNull();
    expect(selectPinnedReviewLensComponent(
      [component(), component()],
      exactPin,
    )).toBeNull();
    expect(selectPinnedReviewLensComponent(
      [component({ asset_url: undefined, legacy_context: true })],
      exactPin,
    )).toBeNull();
  });
});
