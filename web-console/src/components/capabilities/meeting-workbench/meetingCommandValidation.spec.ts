import { describe, expect, it } from 'vitest';

import {
  formatCommandContextRole,
  getGuidanceRequiredRoles,
  getMissingCommandContextRoles,
} from './meetingCommandValidation';
import type { MeetingNode, MeetingObjectActionEntry } from './meetingWorkbenchTypes';

const guidanceNode: MeetingNode = {
  id: 'guidance-1',
  eyebrow: 'Guidance',
  title: 'Director framing',
  detail: 'Plan the next beat',
  status: 'ready',
  kind: 'group',
  lane: 'graph',
  metadata: {
    required_roles: ['target', 'character', 'target'],
  },
};

describe('meetingCommandValidation', () => {
  it('reads de-duplicated required roles from guidance metadata', () => {
    expect(getGuidanceRequiredRoles(guidanceNode)).toEqual(['target', 'character']);
  });

  it('falls back to target when guidance projects a target ref without explicit roles', () => {
    expect(getGuidanceRequiredRoles({
      ...guidanceNode,
      metadata: {
        target_ref: {
          uri: 'mindscape://fixture_pack/storyboard/target_01',
          owner_pack: 'fixture_pack',
          object_kind: 'storyboard',
          object_id: 'target_01',
        },
      },
    })).toEqual(['target']);
  });

  it('reports missing required roles against object action entries', () => {
    const entries: MeetingObjectActionEntry[] = [
      {
        role: 'source',
        ref: {
          uri: 'mindscape://ig/reference/ref_global',
          owner_pack: 'ig',
          object_kind: 'reference',
          object_id: 'ref_global',
        },
      },
      {
        role: 'target',
        ref: {
          uri: 'mindscape://pd/storyboard/storyboard_01',
          owner_pack: 'pd',
          object_kind: 'storyboard',
          object_id: 'storyboard_01',
        },
      },
    ];

    expect(getMissingCommandContextRoles(['source', 'target', 'character'], entries)).toEqual(['character']);
    expect(formatCommandContextRole('character')).toBe('Character');
  });
});
