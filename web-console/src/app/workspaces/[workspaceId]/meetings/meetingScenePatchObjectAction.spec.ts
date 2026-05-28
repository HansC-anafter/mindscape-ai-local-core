import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  applyMeetingScenePatchObjectAction,
  getMeetingScenePatchObjectActionDisabledReason,
} from './meetingScenePatchObjectAction';
import type { MeetingSession } from './meetingRecords.types';

const OWNER_PACK = ['performance', 'direction'].join('_');
const DIRECT_CAPABILITY_ROUTE = ['/api/v1/capabilities', OWNER_PACK].join('/');

const session: MeetingSession = {
  id: 'mtg_scene_patch',
  workspace_id: 'ws_scene',
  started_at: '2026-05-28T00:00:00Z',
  is_active: false,
  status: 'completed',
  meeting_type: 'director_review',
  agenda: [],
  success_criteria: [],
  round_count: 1,
  max_rounds: 1,
  action_items: [],
  decisions: [],
  minutes_md: '',
  metadata: {
    addressable_object_layer: {
      context_entries: [
        {
          role: 'source',
          ref: {
            uri: `mindscape://${OWNER_PACK}/storyboard_scene/ds_1:art_1:sc01`,
            owner_pack: OWNER_PACK,
            object_kind: 'storyboard_scene',
            object_id: 'ds_1:art_1:sc01',
            workspace_id: 'ws_scene',
            selector: {
              selector_type: 'storyboard_scene',
              scene_id: 'sc01',
            },
            source_surface: `${OWNER_PACK}.storyboard_strip`,
          },
        },
      ],
    },
  },
};

describe('meetingScenePatchObjectAction', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn(async (input) => {
      const url = String(input);
      if (url.endsWith('/object-actions/plan')) {
        return new Response(
          JSON.stringify({
            workspace_id: 'ws_scene',
            status: 'planned',
            selected_affordance: {
              verb: 'apply_storyboard_scene_patch',
              planner_backend: 'owner_pack:plan_storyboard_scene_patch',
              executor_backend: 'owner_pack:execute_storyboard_scene_patch',
            },
            request_plan: {
              action_plan_id: 'oap_scene_patch',
              request_context: {
                scene_id: 'sc01',
              },
            },
          }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          },
        );
      }
      return new Response(
        JSON.stringify({
          workspace_id: 'ws_scene',
          status: 'succeeded',
          closure: {
            status: 'succeeded',
            action_plan_id: 'oap_scene_patch',
          },
          executor_result: {
            artifact: {
              artifact_id: 'art_patched',
            },
            outputs: {
              object_action_closure: {
                status: 'succeeded',
              },
            },
          },
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        },
      );
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('plans and invokes scene patch through workspace object-actions only', async () => {
    expect(getMeetingScenePatchObjectActionDisabledReason(session, 'ws_scene', 'sc01')).toBeNull();

    const result = await applyMeetingScenePatchObjectAction({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_scene',
      session,
      sceneId: 'sc01',
      artifactId: 'art_1',
      storyboardScenePatch: {
        scene_id: 'sc01',
        source_scene_id: 'sc01',
      },
    });

    expect(result.tone).toBe('success');
    expect(global.fetch).toHaveBeenCalledTimes(2);
    const [planUrl, planInit] = vi.mocked(global.fetch).mock.calls[0];
    const [invokeUrl] = vi.mocked(global.fetch).mock.calls[1];
    expect(String(planUrl)).toBe('http://api.test/api/v1/workspaces/ws_scene/object-actions/plan');
    expect(String(invokeUrl)).toBe('http://api.test/api/v1/workspaces/ws_scene/object-actions/invoke');
    expect(String(planUrl)).not.toContain(DIRECT_CAPABILITY_ROUTE);
    expect(String(invokeUrl)).not.toContain(DIRECT_CAPABILITY_ROUTE);

    const planBody = JSON.parse(String(planInit?.body));
    expect(planBody.affordance_verb).toBe('apply_storyboard_scene_patch');
    expect(planBody.write_mode).toBe('staged');
    expect(planBody.entries).toHaveLength(1);
    expect(planBody.entries[0].role).toBe('target');
    expect(planBody.entries[0].ref.owner_pack).toBe(OWNER_PACK);
    expect(planBody.entries[0].ref.object_kind).toBe('storyboard_scene');
    expect(planBody.entries[0].ref.selector.scene_id).toBe('sc01');
    expect(planBody.request_context.storyboard_scene_patch).toEqual({
      scene_id: 'sc01',
      source_scene_id: 'sc01',
    });
  });

  it('blocks dispatch when no canonical matching storyboard_scene ref exists', async () => {
    const reason = getMeetingScenePatchObjectActionDisabledReason(session, 'ws_scene', 'sc99');
    expect(reason).toContain('No canonical storyboard_scene ObjectRef');

    const result = await applyMeetingScenePatchObjectAction({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_scene',
      session,
      sceneId: 'sc99',
      storyboardScenePatch: {
        scene_id: 'sc99',
      },
    });

    expect(result.tone).toBe('error');
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
