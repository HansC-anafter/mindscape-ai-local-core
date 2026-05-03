import { describe, expect, it } from 'vitest';

import { buildLedgerIntentText } from './meetingCommandLedger';
import type { MeetingObjectActionEntry } from './meetingWorkbenchTypes';

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
];

describe('meetingCommandLedger', () => {
  it('strips legacy UI mention tokens before sending server grammar text', () => {
    expect(
      buildLedgerIntentText(
        'Send asset @pack:visual_audit @storyboard:manual @character:manual_card',
        entries,
      ),
    ).toBe('Send asset');
  });

  it('falls back to role-bearing object refs when command text is only mentions', () => {
    expect(buildLedgerIntentText('@pack:visual_audit @storyboard:manual', entries)).toBe(
      'mindscape://ig/reference/ref_global',
    );
  });
});
