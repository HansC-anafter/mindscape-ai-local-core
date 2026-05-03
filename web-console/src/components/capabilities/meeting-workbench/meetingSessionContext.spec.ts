import { describe, expect, it } from 'vitest';

import {
  buildSessionAttachResponse,
  buildSessionObjectSummary,
  buildSessionSelection,
  getSessionDisplayTitle,
  getSessionSearchCorpus,
  readAolSessionMetadata,
} from './meetingSessionContext';
import type { MeetingSessionSummary } from './meetingWorkbenchTypes';

const session: MeetingSessionSummary = {
  id: 'mtg_global',
  workspace_id: 'ws-global',
  status: 'active',
  meeting_type: 'aol_runtime',
  agenda: ['Review IG reference'],
  started_at: '2026-05-02T00:00:00Z',
  metadata: {
    addressable_object_layer: {
      status: 'materialized',
      intent_summary: 'Use an IG reference in a PD storyboard',
      context_attachments: [
        {
          object_ref: {
            uri: 'mindscape://ig/reference/ref_global',
            owner_pack: 'ig',
            object_kind: 'reference',
            object_id: 'ref_global',
            source_surface: 'ig.references_grid',
          },
          object_summary: {
            title: 'Global Reference',
            subtitle: 'IG source',
            summary_text: 'A reference image for production direction',
            status: 'ready',
            labels: ['ig', 'reference'],
            owner_surface_url: '/workspaces/ws-global/capabilities/ig',
          },
        },
      ],
      context_entries: [
        {
          role: 'source',
          ref: {
            uri: 'mindscape://ig/reference/ref_global',
            owner_pack: 'ig',
            object_kind: 'reference',
            object_id: 'ref_global',
            source_surface: 'ig.references_grid',
          },
        },
      ],
      staged_refs: [
        {
          uri: 'mindscape://pd/storyboard/pd_manual',
          owner_pack: 'pd',
          object_kind: 'storyboard',
          object_id: 'pd_manual',
        },
      ],
      review_routes: ['/workspaces/ws-global/capabilities/pd'],
    },
  },
};

describe('meetingSessionContext', () => {
  it('reads AOL session metadata from meeting summaries', () => {
    expect(readAolSessionMetadata(session)).toMatchObject({
      status: 'materialized',
      intent_summary: 'Use an IG reference in a PD storyboard',
    });
    expect(readAolSessionMetadata({ id: 'mtg_empty' })).toBeNull();
  });

  it('builds object summary and selection from the first AOL attachment', () => {
    expect(buildSessionObjectSummary(session)).toEqual({
      ref: {
        uri: 'mindscape://ig/reference/ref_global',
        owner_pack: 'ig',
        object_kind: 'reference',
        object_id: 'ref_global',
        workspace_id: 'ws-global',
        version: null,
        selector: null,
        source_surface: 'ig.references_grid',
      },
      title: 'Global Reference',
      subtitle: 'IG source',
      summary_text: 'A reference image for production direction',
      status: 'ready',
      labels: ['ig', 'reference'],
      owner_surface_url: '/workspaces/ws-global/capabilities/ig',
    });

    expect(buildSessionSelection(session)).toEqual({
      ownerPack: 'ig',
      objectKind: 'reference',
      objectId: 'ref_global',
      version: undefined,
      selector: undefined,
      sourceSurface: 'ig.references_grid',
      label: 'Global Reference',
      role: 'source',
    });
  });

  it('builds attach response projection from AOL context entries and staged refs', () => {
    expect(buildSessionAttachResponse(session, 'fallback-workspace')).toEqual({
      workspace_id: 'ws-global',
      meeting_id: 'mtg_global',
      status: 'materialized',
      attachments: [
        {
          role: 'source',
          ref: {
            uri: 'mindscape://ig/reference/ref_global',
            owner_pack: 'ig',
            object_kind: 'reference',
            object_id: 'ref_global',
            workspace_id: 'ws-global',
            version: null,
            selector: null,
            source_surface: 'ig.references_grid',
          },
          projection_level: 'meeting',
        },
      ],
      target_ref: null,
      staged_refs: [
        {
          uri: 'mindscape://pd/storyboard/pd_manual',
          owner_pack: 'pd',
          object_kind: 'storyboard',
          object_id: 'pd_manual',
          workspace_id: 'ws-global',
          version: null,
          selector: null,
          source_surface: null,
        },
      ],
      review_routes: ['/workspaces/ws-global/capabilities/pd'],
      errors: [],
    });
  });

  it('uses object summary for display title and searchable corpus', () => {
    expect(getSessionDisplayTitle(session)).toBe('Global Reference');
    expect(getSessionSearchCorpus(session)).toContain('global reference');
    expect(getSessionSearchCorpus(session)).toContain('use an ig reference in a pd storyboard');
  });
});
