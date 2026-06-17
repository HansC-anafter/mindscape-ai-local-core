import type { CapabilityWorkbenchCommandHeaderProps } from './capability-workbench';
import { describe, expect, it } from 'vitest';
import {
  assertCapabilityWorkbenchInfoMetadata,
  isCapabilityWorkbenchInfoMetadata,
  type CapabilityWorkbenchInfoMetadata,
} from './capability-workbench';

const VALID_METADATA: CapabilityWorkbenchInfoMetadata = {
  schemaVersion: 'capability_workbench_info_metadata.v1',
  capability: {
    code: 'performance_direction',
    label: 'Performance Direction',
  },
  workspace: {
    id: 'ws_demo',
    label: 'Demo workspace',
  },
  primaryObject: {
    kind: 'storyboard',
    id: 'sb_demo',
    label: 'Storyboard demo',
    ownerCapability: 'performance_direction',
  },
  session: {
    id: 'ds_demo',
    kind: 'direction_session',
    status: 'active',
  },
  artifact: {
    id: 'da_demo',
    kind: 'director_artifact',
    label: 'Director artifact',
  },
  selection: {
    sceneId: 'sc01',
    shotId: 'shot01',
    mode: 'boards',
    department: 'direction',
  },
  references: [
    {
      key: 'workspace',
      label: 'Workspace',
      value: 'ws_demo',
      copyValue: 'ws_demo',
    },
  ],
  status: [
    {
      key: 'preview_state',
      label: 'Preview state',
      value: 'idle',
      tone: 'neutral',
    },
  ],
};

describe('capability workbench contracts', () => {
  it('accepts the single v1 info metadata shape', () => {
    expect(isCapabilityWorkbenchInfoMetadata(VALID_METADATA)).toBe(true);
    expect(assertCapabilityWorkbenchInfoMetadata(VALID_METADATA)).toBe(VALID_METADATA);
  });

  it('rejects invalid primary object kinds and status tones', () => {
    expect(isCapabilityWorkbenchInfoMetadata({
      ...VALID_METADATA,
      primaryObject: {
        ...VALID_METADATA.primaryObject,
        kind: 'scene',
      },
    })).toBe(false);
    expect(isCapabilityWorkbenchInfoMetadata({
      ...VALID_METADATA,
      status: [
        {
          key: 'preview_state',
          label: 'Preview state',
          value: 'idle',
          tone: 'blue',
        },
      ],
    })).toBe(false);
  });

  it('keeps command header props separate from metadata payloads', () => {
    const validHeaderProps: CapabilityWorkbenchCommandHeaderProps = {
      brandSlot: 'Performance Direction',
      modeSlot: 'Boards',
      utilitySlot: 'Load',
      mobileCollapsible: true,
      mobileDefaultCollapsed: true,
    };
    expect(validHeaderProps.brandSlot).toBe('Performance Direction');

    const invalidHeaderProps: CapabilityWorkbenchCommandHeaderProps = {
      brandSlot: 'Performance Direction',
      // @ts-expect-error metadata is intentionally not a command header prop.
      metadata: VALID_METADATA,
    };
    expect(invalidHeaderProps.brandSlot).toBe('Performance Direction');
  });
});
