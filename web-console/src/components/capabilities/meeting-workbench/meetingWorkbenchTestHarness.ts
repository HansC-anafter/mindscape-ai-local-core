import { afterEach, beforeEach, vi } from 'vitest';

import { registryCompletionRecords, summary } from './meetingWorkbenchTestData';
import {
  createEmptyExecutionGraphResponse,
  createExecutionGraphResponse,
  createObjectGraphProjectResponse,
} from './meetingWorkbenchGraphFixtureResponses';

export function installAOLMeetingBottomShellTestHarness() {
  const originalFetch = global.fetch;

  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', {
      configurable: true,
      value: vi.fn(),
    });
    global.fetch = vi.fn(async (input, init) => {
      const url = String(input);
      if (url.includes('/api/v1/playbooks/?')) {
        return new Response(
          JSON.stringify([
            {
              playbook_code: 'visual_audit',
              name: 'Visual Audit',
              description: 'Audit visual references',
              capability_code: 'ig',
              required_tools: ['canva'],
            },
            {
              playbook_code: 'generate_reels_asset',
              name: 'Generate Reels Asset',
              description: 'Generate performance direction reels assets',
              capability_code: 'performance_direction',
              required_tools: ['comfyui'],
            },
          ]),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          },
        );
      }
      if (url.includes('/api/v1/workspaces/ws-global/objects/complete?')) {
        const parsedUrl = new URL(url, 'http://api.test');
        const query = (parsedUrl.searchParams.get('query') || '').toLowerCase();
        const records = registryCompletionRecords;

        const results = records.filter((record) => {
          const haystack = `${record.token} ${record.label} ${record.description} ${record.owner_pack} ${record.object_kind}`.toLowerCase();
          return !query || haystack.includes(query);
        });

        return new Response(JSON.stringify({
          workspace_id: 'ws-global',
          query,
          results,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/workspaces/ws-global/object-actions/plan')) {
        return new Response(JSON.stringify({
          workspace_id: 'ws-global',
          status: 'planned',
          selected_affordance: {
            verb: 'generate_reels_asset',
            label: 'Generate reels asset',
            object_kinds: ['storyboard_scene'],
            input_schema: { type: 'object' },
            output_schema: { type: 'object' },
            required_roles: ['source', 'target', 'character'],
            write_modes: ['staged'],
            planner_backend: 'capabilities.performance_direction.services.aol:plan_reels_asset',
            executor_backend: 'capabilities.performance_direction.services.aol:execute_reels_asset',
          },
          missing_roles: [],
          request_plan: {
            steps: ['load_source_reference', 'patch_storyboard_scene'],
          },
          errors: [],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/workspaces/ws-global/meetings/mtg_global/commands')) {
        const requestBody = JSON.parse(String(init?.body || '{}'));
        const omitDispatchResult = requestBody?.intent_text === 'No dispatch result fixture';
        const routeObjectAction = requestBody?.metadata?.dispatch_mode === 'route_object_action';
        const routePlaybook = requestBody?.metadata?.dispatch_mode === 'route_playbook';
        const routeMeetingOrchestration = requestBody?.metadata?.dispatch_mode === 'route_meeting_orchestration';
        const routeChat = requestBody?.metadata?.dispatch_mode === 'route_chat';
        const acceptedTaskId = routeObjectAction
          ? 'exec-invoked'
          : routePlaybook
            ? 'exec-playbook'
            : routeMeetingOrchestration
              ? 'task-meeting'
              : routeChat
                ? 'cmd-ledger-global'
                : undefined;
        return new Response(JSON.stringify({
          workspace_id: 'ws-global',
          meeting_id: 'mtg_global',
          command_id: 'cmd-ledger-global',
          status: routeObjectAction || routeMeetingOrchestration ? 'completed' : 'accepted',
          command: {
            command_id: 'cmd-ledger-global',
            workspace_id: 'ws-global',
            meeting_id: 'mtg_global',
            thread_id: 'mtg_global',
            origin_surface: 'ig.references_grid',
            actor: 'user',
            intent_text: 'Fixture command',
            context_objects: [],
            expected_outputs: [],
            write_mode: 'recommendation_only',
            status: routeObjectAction || routeMeetingOrchestration ? 'completed' : 'accepted',
            accepted_task_id: acceptedTaskId,
            metadata: {},
            created_at: '2026-04-27T01:01:00Z',
            updated_at: '2026-04-27T01:01:00Z',
          },
          dispatch_result: omitDispatchResult
            ? null
            : routeObjectAction
              ? {
                object_action: {
                  status: 'succeeded',
                  execution_id: 'exec-invoked',
                  task_id: 'exec-invoked',
                },
              }
              : routePlaybook
                ? {
                  playbook: {
                    status: 'accepted',
                    task_id: 'exec-playbook',
                    triggered_playbook: {
                      playbook_code: requestBody?.requested_action?.playbook_code,
                      execution_id: 'exec-playbook',
                      status: 'triggered',
                    },
                  },
                }
                : routeMeetingOrchestration
                  ? {
                    meeting_orchestration: {
                      status: 'completed',
                      task_ir_id: 'task-meeting',
                      artifact_landing_status: 'pending',
                      request_contract_aol_metadata: {
                        selected_guidance_ids: requestBody?.metadata?.selected_guidance_ids || [],
                        candidate_playbooks: requestBody?.requested_action?.playbook_code
                          ? [
                            {
                              source: 'selected_pack_tool',
                              pack_code: requestBody?.requested_action?.pack_code,
                              playbook_code: requestBody?.requested_action?.playbook_code,
                            },
                          ]
                          : [],
                      },
                    },
                  }
                : routeChat
                  ? {
                    chat: {
                      status: 'accepted',
                      task_id: 'cmd-ledger-global',
                      event_id: 'cmd-ledger-global',
                      thread_id: 'mtg_global',
                    },
                  }
                  : null,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/workspaces/ws-global/object-actions/invoke')) {
        return new Response(JSON.stringify({
          workspace_id: 'ws-global',
          status: 'succeeded',
          action_plan_id: 'oap_frontend_test',
          execution_id: 'exec-invoked',
          task_id: 'exec-invoked',
          closure: {
            status: 'succeeded',
            output_refs: [
              {
                uri: 'mindscape://performance_direction/generated_reels_asset/exec-invoked',
                owner_pack: 'performance_direction',
                object_kind: 'generated_reels_asset',
                object_id: 'exec-invoked',
              },
            ],
          },
          executor_result: {
            status: 'completed',
          },
          errors: [],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/workspaces/ws-global/object-graph/project')) {
        return createObjectGraphProjectResponse(init);
      }
      if (url.includes('/api/v1/workspaces/ws-global/meeting-sessions?limit=100')) {
        return new Response(JSON.stringify({
          sessions: [
            {
              id: 'mtg_global',
              workspace_id: 'ws-global',
              started_at: '2026-04-27T01:00:00Z',
              is_active: true,
              status: 'active',
              meeting_type: 'direction',
              agenda: ['Global Reference'],
              metadata: {
                addressable_object_layer: {
                  status: 'attached',
                  context_entries: [
                    {
                      role: 'source',
                      ref: summary.ref,
                    },
                  ],
                  context_attachments: [
                    {
                      role: 'source',
                      object_ref: summary.ref,
                      object_summary: {
                        title: summary.title,
                        summary_text: summary.summary_text,
                        labels: summary.labels,
                        owner_surface_url: summary.owner_surface_url,
                      },
                    },
                  ],
                  staged_refs: [],
                  review_routes: [],
                },
              },
            },
            {
              id: 'mtg_other',
              workspace_id: 'ws-global',
              started_at: '2026-04-27T02:00:00Z',
              is_active: true,
              status: 'active',
              meeting_type: 'direction',
              agenda: ['Other Reference'],
              metadata: {},
            },
          ],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/workspaces/ws-global/meeting-sessions/mtg_global/events?limit=120')) {
        return new Response(JSON.stringify({
          events: [
            {
              id: 'event_user',
              timestamp: '2026-04-27T01:01:00Z',
              actor: 'user',
              event_type: 'message',
              payload: {
                message: 'Create a 90 second reels script from this reference',
              },
              metadata: {},
            },
            {
              id: 'event_stage',
              timestamp: '2026-04-27T01:01:05Z',
              actor: 'assistant',
              event_type: 'pipeline_stage',
              payload: {
                stage: 'context_building',
                message: 'Preparing context',
                status: 'running',
              },
              metadata: {},
            },
            {
              id: 'event_result',
              timestamp: '2026-04-27T01:01:20Z',
              actor: 'assistant',
              event_type: 'message',
              payload: {
                message: '0-10: opening shot\\n10-20: visual beat',
              },
              metadata: {},
            },
            ...Array.from({ length: 20 }, (_, index) => ({
              id: `event_action_${index + 1}`,
              timestamp: `2026-04-27T01:02:${String(index).padStart(2, '0')}Z`,
              actor: 'system',
              event_type: 'action_item',
              payload: {
                title: `Governance action item ${index + 1}`,
              },
              metadata: {},
            })),
          ],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/workspaces/ws-global/meetings/mtg_global/execution-graph?limit=200')) {
        return createExecutionGraphResponse();
      }
      if (url.includes('/api/v1/workspaces/ws-global/meetings/') && url.includes('/execution-graph?limit=200')) {
        return createEmptyExecutionGraphResponse();
      }
      if (url.includes('/api/v1/workspaces/ws-global/artifacts?thread_id=mtg_global&limit=80')) {
        return new Response(JSON.stringify({
          artifacts: [
            {
              id: 'artifact_result',
              workspace_id: 'ws-global',
              thread_id: 'mtg_global',
              execution_id: 'exec_result',
              playbook_code: 'external_agent',
              artifact_type: 'data',
              title: 'Task Result: exec_result',
              summary: 'Landed result artifact',
              content: {},
              metadata: {
                source: 'task_runner',
                landing: {
                  artifact_dir: '/tmp/artifacts/exec_result',
                },
              },
              created_at: '2026-04-27T01:01:30Z',
            },
          ],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/workspaces/ws-global/artifacts?thread_id=')) {
        return new Response(JSON.stringify({ artifacts: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/events?thread_id=')) {
        return new Response(JSON.stringify({ events: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/meeting-sessions/') && url.includes('/events?limit=120')) {
        return new Response(JSON.stringify({ events: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/workspaces/ws-global/agents')) {
        return new Response(JSON.stringify({ agents: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/settings/model-route-registry/workspace-executor?workspace_id=ws-global')) {
        return new Response(JSON.stringify({
          primary_executor_runtime: null,
          surfaces: {},
          dispatch_chain: [],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ task_id: 'task-accepted' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

}
