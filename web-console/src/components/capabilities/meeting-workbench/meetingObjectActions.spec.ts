import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  invokeObjectAction,
  isPlannedObjectActionPlan,
  requestObjectActionPlan,
} from './meetingObjectActions';
import type { MeetingObjectActionEntry } from './meetingWorkbenchTypes';

const context = {
  apiUrl: 'http://api.test/',
  workspaceId: 'ws global',
  meetingId: 'mtg_global',
  commandId: 'cmd_global',
  sourceSurface: 'ig.references_grid',
  selectedObjectUri: 'mindscape://ig/reference/ref_global',
};

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
      uri: 'mindscape://pd/storyboard/storyboard_1',
      owner_pack: 'pd',
      object_kind: 'storyboard',
      object_id: 'storyboard_1',
    },
  },
];

describe('meetingObjectActions', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn(async () => {
      return new Response(JSON.stringify({ status: 'planned', request_plan: { action: 'attach' } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('skips object action planning until there are at least two entries', async () => {
    const result = await requestObjectActionPlan(context, 'Attach this reference', entries.slice(0, 1));

    expect(result).toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('posts the planning request with meeting and selected-object context', async () => {
    const result = await requestObjectActionPlan(context, 'Attach this reference', entries);

    expect(result).toEqual({ status: 'planned', request_plan: { action: 'attach' } });
    expect(global.fetch).toHaveBeenCalledTimes(1);

    const [url, init] = vi.mocked(global.fetch).mock.calls[0];
    expect(String(url)).toBe('http://api.test/api/v1/workspaces/ws%20global/object-actions/plan');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      instruction: 'Attach this reference',
      meeting_id: 'mtg_global',
      entries,
      request_context: {
        source_surface: 'ig.references_grid',
        selected_object_uri: 'mindscape://ig/reference/ref_global',
        command_id: 'cmd_global',
      },
    });
  });

  it('returns a rejected plan payload when planning fails', async () => {
    global.fetch = vi.fn(async () => {
      return new Response(JSON.stringify({ detail: { message: 'No compatible object action' } }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;

    const result = await requestObjectActionPlan(context, 'Attach this reference', entries);

    expect(result).toEqual({
      status: 'rejected',
      errors: [
        {
          code: 'object_action_plan_failed',
          message: 'No compatible object action',
        },
      ],
    });
  });

  it('recognizes planned object action payloads', () => {
    expect(isPlannedObjectActionPlan({ status: 'planned', request_plan: { action: 'attach' } })).toBe(true);
    expect(isPlannedObjectActionPlan({ status: 'planned' })).toBe(false);
    expect(isPlannedObjectActionPlan({ status: 'rejected', request_plan: { action: 'attach' } })).toBe(false);
  });

  it('posts invoke payloads through the API fallback helper', async () => {
    global.fetch = vi.fn(async () => {
      return new Response(JSON.stringify({ status: 'succeeded', execution_id: 'exec_123' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;

    const objectActionPlan = { status: 'planned', request_plan: { action: 'attach' } };
    const result = await invokeObjectAction(context, 'Attach this reference', objectActionPlan, entries);

    expect(result).toEqual({ status: 'succeeded', execution_id: 'exec_123' });
    expect(global.fetch).toHaveBeenCalledTimes(1);

    const [url, init] = vi.mocked(global.fetch).mock.calls[0];
    expect(String(url)).toBe('http://api.test/api/v1/workspaces/ws%20global/object-actions/invoke');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      instruction: 'Attach this reference',
      meeting_id: 'mtg_global',
      thread_id: 'mtg_global',
      object_action_plan: objectActionPlan,
      entries,
      request_context: {
        source_surface: 'ig.references_grid',
        selected_object_uri: 'mindscape://ig/reference/ref_global',
        command_id: 'cmd_global',
      },
    });
  });
});
