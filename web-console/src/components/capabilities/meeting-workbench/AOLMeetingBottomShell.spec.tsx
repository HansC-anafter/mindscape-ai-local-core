import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AOLMeetingBottomShell from './AOLMeetingBottomShell';

const summary = {
  ref: {
    uri: 'mindscape://ig/reference/ref_global',
    owner_pack: 'ig',
    object_kind: 'reference',
    object_id: 'ref_global',
    source_surface: 'ig.references_grid',
  },
  title: 'Global Reference',
  summary_text: 'Shared host selection',
  labels: ['ig', 'reference'],
  owner_surface_url: '/workspaces/ws-global/capabilities/ig',
};

const attachResponse = {
  workspace_id: 'ws-global',
  meeting_id: 'mtg_global',
  status: 'attached' as const,
  attachments: [],
  staged_refs: [],
  review_routes: [],
  errors: [],
};

describe('AOLMeetingBottomShell', () => {
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
    global.fetch = vi.fn(async (input) => {
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
        const records = [
          {
            id: 'fixture_pack:storyboard:fx_session_1',
            token: '@storyboard:fx_session_1',
            label: 'Fixture storyboard',
            description: 'Neutral registry storyboard',
            owner_pack: 'fixture_pack',
            object_kind: 'storyboard',
            score: 1,
            ref: {
              uri: 'mindscape://fixture_pack/storyboard/fx_session_1',
              owner_pack: 'fixture_pack',
              object_kind: 'storyboard',
              object_id: 'fx_session_1',
              workspace_id: 'ws-global',
              selector: { selector_type: 'object_root' },
            },
            metadata: {
              affordance_verbs: ['produce_asset'],
            },
          },
          {
            id: 'fixture_pack:storyboard_scene:fx_session_1:fx_artifact_1:fx_scene',
            token: '@storyboard_scene:fx_session_1:fx_artifact_1:fx_scene',
            label: 'Fixture storyboard / fx_scene',
            description: 'Neutral registry storyboard scene',
            owner_pack: 'fixture_pack',
            object_kind: 'storyboard_scene',
            score: 1,
            ref: {
              uri: 'mindscape://fixture_pack/storyboard_scene/fx_session_1:fx_artifact_1:fx_scene',
              owner_pack: 'fixture_pack',
              object_kind: 'storyboard_scene',
              object_id: 'fx_session_1:fx_artifact_1:fx_scene',
              workspace_id: 'ws-global',
              selector: {
                selector_type: 'storyboard_scene',
                scene_id: 'fx_scene',
              },
            },
            metadata: {
              affordance_verbs: ['produce_asset'],
            },
          },
          {
            id: 'fixture_pack:character_package:fixture_character_pkg',
            token: '@character:fixture_character_pkg',
            label: 'Fixture Character',
            description: 'Neutral registry character package',
            owner_pack: 'fixture_pack',
            object_kind: 'character_package',
            score: 1,
            ref: {
              uri: 'mindscape://fixture_pack/character_package/fixture_character_pkg',
              owner_pack: 'fixture_pack',
              object_kind: 'character_package',
              object_id: 'fixture_character_pkg',
              workspace_id: 'ws-global',
              selector: { selector_type: 'object_root' },
            },
            metadata: {
              affordance_verbs: [],
            },
          },
          {
            id: 'fixture_pack:character_card:fixture_character_card',
            token: '@character_card:fixture_character_card',
            label: 'Fixture Character Card',
            description: 'Neutral registry character card',
            owner_pack: 'fixture_pack',
            object_kind: 'character_card',
            score: 1,
            ref: {
              uri: 'mindscape://fixture_pack/character_card/fixture_character_card',
              owner_pack: 'fixture_pack',
              object_kind: 'character_card',
              object_id: 'fixture_character_card',
              workspace_id: 'ws-global',
              selector: { selector_type: 'object_root' },
            },
            metadata: {
              affordance_verbs: [],
            },
          },
          {
            id: 'performance_direction:storyboard:pd_session_1',
            token: '@storyboard:pd_session_1',
            label: 'Yoga storyboard',
            description: '90s yoga reels storyboard',
            owner_pack: 'performance_direction',
            object_kind: 'storyboard',
            score: 1,
            ref: {
              uri: 'mindscape://performance_direction/storyboard/pd_session_1',
              owner_pack: 'performance_direction',
              object_kind: 'storyboard',
              object_id: 'pd_session_1',
              workspace_id: 'ws-global',
              selector: { selector_type: 'object_root' },
            },
            metadata: {
              affordance_verbs: ['generate_reels_asset'],
            },
          },
          {
            id: 'performance_direction:storyboard_scene:pd_session_1:pd_artifact_1:sc02',
            token: '@storyboard_scene:pd_session_1:pd_artifact_1:sc02',
            label: 'Yoga storyboard / sc02',
            description: 'performance_direction storyboard scene',
            owner_pack: 'performance_direction',
            object_kind: 'storyboard_scene',
            score: 1,
            ref: {
              uri: 'mindscape://performance_direction/storyboard_scene/pd_session_1:pd_artifact_1:sc02',
              owner_pack: 'performance_direction',
              object_kind: 'storyboard_scene',
              object_id: 'pd_session_1:pd_artifact_1:sc02',
              workspace_id: 'ws-global',
              selector: {
                selector_type: 'storyboard_scene',
                scene_id: 'sc02',
              },
            },
            metadata: {
              affordance_verbs: ['generate_reels_asset'],
            },
          },
          {
            id: 'performance_direction:storyboard_scene:pd_session_registry:latest:sc03',
            token: '@storyboard_scene:pd_session_registry:latest:sc03',
            label: 'Registry storyboard / sc03',
            description: 'Registry-backed storyboard scene',
            owner_pack: 'performance_direction',
            object_kind: 'storyboard_scene',
            score: 1,
            ref: {
              uri: 'mindscape://performance_direction/storyboard_scene/pd_session_registry:latest:sc03',
              owner_pack: 'performance_direction',
              object_kind: 'storyboard_scene',
              object_id: 'pd_session_registry:latest:sc03',
              workspace_id: 'ws-global',
              selector: {
                selector_type: 'storyboard_scene',
                scene_id: 'sc03',
              },
            },
            metadata: {
              affordance_verbs: ['patch_storyboard'],
            },
          },
          {
            id: 'character_training:character_package:chacto_hero_pkg',
            token: '@character:chacto_hero_pkg',
            label: 'Chacto Hero',
            description: 'character_training package',
            owner_pack: 'character_training',
            object_kind: 'character_package',
            score: 1,
            ref: {
              uri: 'mindscape://character_training/character_package/chacto_hero_pkg',
              owner_pack: 'character_training',
              object_kind: 'character_package',
              object_id: 'chacto_hero_pkg',
              workspace_id: 'ws-global',
              selector: { selector_type: 'object_root' },
            },
            metadata: {
              affordance_verbs: [],
            },
          },
          {
            id: 'character_training:character_card:card_chacto',
            token: '@character_card:card_chacto',
            label: 'Chacto Persona',
            description: 'character_training character card',
            owner_pack: 'character_training',
            object_kind: 'character_card',
            score: 1,
            ref: {
              uri: 'mindscape://character_training/character_card/card_chacto',
              owner_pack: 'character_training',
              object_kind: 'character_card',
              object_id: 'card_chacto',
              workspace_id: 'ws-global',
              selector: { selector_type: 'object_root' },
            },
            metadata: {
              affordance_verbs: [],
            },
          },
        ];
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
        return new Response(JSON.stringify({
          workspace_id: 'ws-global',
          projections: [
            {
              ref: summary.ref,
              summary,
              node_kind: 'reference',
              relations: [
                {
                  relation_kind: 'relates_to',
                  direction: 'outbound',
                  target_ref: {
                    uri: 'mindscape://fixture_pack/generic_object/object_open',
                    owner_pack: 'fixture_pack',
                    object_kind: 'generic_object',
                    object_id: 'object_open',
                    workspace_id: 'ws-global',
                  },
                },
              ],
              metadata: {
                projection_source: 'owner_pack_graph_projection',
              },
            },
          ],
          errors: [],
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
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
        return new Response(JSON.stringify({
          workspace_id: 'ws-global',
          meeting_id: 'mtg_global',
          nodes: [
            {
              id: 'command-oap-global',
              eyebrow: 'Command',
              title: 'Produce generic asset',
              detail: 'produce_asset · plan oap-global',
              status: 'ready',
              kind: 'command',
              lane: 'commands',
            },
            {
              id: 'run-task-global',
              eyebrow: 'Run',
              title: 'fixture_runtime',
              detail: 'succeeded · task task-global',
              status: 'ready',
              kind: 'run',
              lane: 'runs',
            },
            {
              id: 'closure-oap-global',
              eyebrow: 'Closure',
              title: 'Action closed',
              detail: '1 outputs · 2 relations',
              status: 'ready',
              kind: 'result',
              lane: 'outputs',
            },
            {
              id: 'relation-rel-output-target',
              eyebrow: 'Provenance',
              title: 'produced',
              detail: 'output -> target · plan oap-global',
              status: 'ready',
              kind: 'result',
              lane: 'outputs',
            },
            {
              id: 'output-object-global',
              eyebrow: 'Output object',
              title: 'generated_asset asset_global',
              detail: 'mindscape://fixture_pack/generated_asset/asset_global',
              status: 'ready',
              kind: 'artifact',
              lane: 'artifacts',
            },
          ],
          edges: [
            {
              id: 'edge-command-run',
              from_id: 'command-oap-global',
              to_id: 'run-task-global',
              type: 'dispatches',
            },
            {
              id: 'edge-run-closure',
              from_id: 'run-task-global',
              to_id: 'closure-oap-global',
              type: 'closes',
            },
            {
              id: 'edge-closure-output',
              from_id: 'closure-oap-global',
              to_id: 'output-object-global',
              type: 'produced',
            },
          ],
          task_count: 1,
          relation_count: 2,
          artifact_count: 1,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.includes('/api/v1/workspaces/ws-global/meetings/') && url.includes('/execution-graph?limit=200')) {
        return new Response(JSON.stringify({
          workspace_id: 'ws-global',
          nodes: [],
          edges: [],
          task_count: 0,
          relation_count: 0,
          artifact_count: 0,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
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

  it('opens as a graph-first bottom shell with collapsed inspector and console', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(screen.getByTestId('aol-meeting-bottom-shell')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-header-toolbar')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-object-context-panel')).toBeNull();
    expect(screen.queryByTestId('meeting-session-strip')).toBeNull();
    expect(screen.getByTestId('meeting-task-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-pack-tool-select')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('meeting-sessions-toggle'));
    expect(await screen.findByTestId('meeting-session-strip')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-session-card-mtg_global')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-session-result-count')).toHaveTextContent('2/2');

    fireEvent.click(screen.getByTestId('meeting-object-context-toggle'));
    expect(screen.queryByTestId('meeting-sessions-popover')).toBeNull();
    expect(screen.getByTestId('meeting-object-context-panel')).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
    expect(screen.getByText('Ready for instruction')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-inspector-panel')).toBeNull();
    expect(screen.queryByTestId('meeting-console-drawer')).toBeNull();
  });

  it('renders meeting-owned execution graph nodes from task closure proof', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/fixture_pack"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(await screen.findByTestId('meeting-graph-node-command-oap-global')).toHaveTextContent(
      'Produce generic asset',
    );
    expect(screen.getByTestId('meeting-graph-lane-commands')).toHaveTextContent('Issued instructions');
    expect(screen.getByTestId('meeting-graph-node-command-event_user')).toHaveTextContent('#1 initial');
    expect(screen.getByTestId('meeting-graph-node-command-oap-global')).toHaveTextContent('#2 inserted');
    expect(screen.getByTestId('meeting-graph-node-run-task-global')).toHaveTextContent('fixture_runtime');
    expect(screen.getByTestId('meeting-graph-node-closure-oap-global')).toHaveTextContent(
      'Action closed',
    );
    expect(screen.getByTestId('meeting-graph-node-relation-rel-output-target')).toHaveTextContent(
      'produced',
    );
    expect(screen.getByTestId('meeting-graph-node-output-object-global')).toHaveTextContent(
      'generated_asset',
    );

    fireEvent.click(screen.getByTestId('meeting-graph-node-command-oap-global'));

    const impactPanel = screen.getByTestId('meeting-command-impact-panel');
    expect(impactPanel).toHaveTextContent('Command impact');
    expect(impactPanel).toHaveTextContent('inserted');
    expect(impactPanel).toHaveTextContent('Edges');
    expect(within(impactPanel).getByText('3')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-node-run-task-global')).toHaveAttribute('data-impact-state', 'related');
    expect(screen.getByTestId('meeting-graph-node-output-object-global')).toHaveAttribute('data-impact-state', 'related');
  });

  it('renders bounded object graph projections in the generic graph lane and inspector', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/fixture_pack"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(await screen.findByTestId('meeting-graph-lane-graph')).toHaveTextContent('Object Graph');
    expect(await screen.findByText('1 bounded relation')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('meeting-inspector-tab-graph'));

    expect(screen.getByTestId('meeting-object-graph-panel')).toHaveTextContent('Bounded object graph');
    expect(screen.getByTestId('meeting-object-graph-panel')).toHaveTextContent('relates_to');
  });

  it('filters meeting sessions from the header popover', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId('meeting-sessions-toggle'));
    fireEvent.change(await screen.findByTestId('meeting-session-search'), {
      target: { value: 'Other Reference' },
    });

    expect(screen.getByTestId('meeting-session-result-count')).toHaveTextContent('1/2');
    expect(screen.getByTestId('meeting-session-card-mtg_other')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-session-card-mtg_global')).toBeNull();
  });

  it('projects persisted meeting events into semantic lanes and collapses noisy action items', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(await screen.findByTestId('meeting-graph-lanes')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-lane-context')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-lane-commands')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-lane-runs')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-lane-outputs')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-lane-artifacts')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-graph-lane-next')).toBeInTheDocument();
    expect(await screen.findByTestId('meeting-graph-node-command-event_user')).toHaveTextContent(
      'Create a 90 second reels script',
    );
    expect(screen.queryByTestId('meeting-graph-node-run-event_stage')).toBeNull();
    expect(screen.getByTestId('meeting-graph-node-result-event_result')).toHaveTextContent('0-10: opening shot');
    expect(screen.getByTestId('meeting-graph-node-group-action-items')).toHaveTextContent('Action Items - 20');
    expect(screen.queryByTestId('meeting-graph-node-event_action_1')).toBeNull();
    expect(await screen.findByTestId('meeting-graph-node-artifact-artifact_result')).toHaveTextContent(
      'Task Result: exec_result',
    );

    fireEvent.click(screen.getByTestId('meeting-graph-node-group-action-items'));
    expect(screen.getByTestId('meeting-inspector-panel')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-trace-panel')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-trace-filter-action_item')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('meeting-trace-event-list')).toHaveTextContent('Governance action item 1');
  });

  it('auto-selects the newest workspace meeting when opened without an object-bound meeting id', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId={null}
        summary={null}
        selection={null}
        attachResponse={null}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('meeting-graph-node-root')).toHaveTextContent('mtg_global');
    });
    expect(screen.getByLabelText('Meeting instruction')).toBeEnabled();
  });

  it('opens one inspector panel at a time inside the bottom shell', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId('meeting-inspector-tab-runtime'));
    expect(screen.getByTestId('meeting-inspector-panel')).toBeInTheDocument();
    expect(within(screen.getByTestId('meeting-inspector-panel')).getByText('Runtime binding')).toBeInTheDocument();
    expect(await screen.findByText('No runtime agents reported.')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('meeting-inspector-tab-session'));
    expect(within(screen.getByTestId('meeting-inspector-panel')).getByText('Workspace')).toBeInTheDocument();
    expect(within(screen.getByTestId('meeting-inspector-panel')).queryByText('Runtime binding')).toBeNull();
  });

  it('supports canvas-level zoom controls for the node graph', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('meeting-canvas-zoom-in'));
    expect(screen.getByText('110%')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('meeting-canvas-zoom-out'));
    expect(screen.getByText('100%')).toBeInTheDocument();
    const canvas = screen.getByTestId('meeting-task-canvas');
    fireEvent.wheel(canvas, { deltaY: -12, deltaX: 0, deltaMode: 0, clientX: 200, clientY: 100 });
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.wheel(canvas, { deltaY: -120, deltaX: 24, deltaMode: 0, clientX: 200, clientY: 100 });
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.wheel(await screen.findByTestId('meeting-graph-node-command-oap-global'), {
      deltaY: -120,
      deltaX: 0,
      deltaMode: 0,
      clientX: 200,
      clientY: 100,
    });
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.wheel(canvas, { deltaY: -120, deltaX: 0, deltaMode: 0, clientX: 200, clientY: 100 });
    expect(screen.getByText('110%')).toBeInTheDocument();
    fireEvent.wheel(canvas, { deltaY: 120, deltaX: 0, deltaMode: 0, clientX: 200, clientY: 100 });
    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('meeting-canvas-fit'));
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('pans the graph canvas by dragging the background', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
    const canvas = screen.getByTestId('meeting-task-canvas');
    const content = screen.getByTestId('meeting-graph-canvas-content');

    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 145, clientY: 125 });

    expect(content).toHaveStyle({ transform: 'translate(45px, 25px) scale(1)' });
  });

  it('opens @ mention picker and inserts pack references into the command bar', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    expect(await screen.findByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
    const input = screen.getByLabelText('Meeting instruction');

    fireEvent.change(input, { target: { value: 'Use @' } });
    expect(screen.getByTestId('meeting-mention-picker')).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByTestId('meeting-mention-option-pack-visual_audit'));

    expect(input).toHaveValue('Use @pack:visual_audit ');
    expect(screen.getByTestId('meeting-pack-tool-select')).toHaveValue('visual_audit');
  });

  it('offers registry-backed storyboards, storyboard scenes, and character targets as command mentions', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    const input = screen.getByLabelText('Meeting instruction');

    fireEvent.change(input, { target: { value: 'Send asset to @performance_di' } });
    expect(
      await screen.findByTestId('meeting-mention-option-registry-performance_direction-storyboard-pd_session_1'),
    ).toHaveTextContent('Yoga storyboard');
    fireEvent.mouseDown(screen.getByTestId('meeting-mention-option-registry-performance_direction-storyboard-pd_session_1'));
    expect(input).toHaveValue('Send asset to @storyboard:pd_session_1 ');

    fireEvent.change(input, { target: { value: 'Patch @sc02' } });
    expect(
      await screen.findByTestId(
        'meeting-mention-option-registry-performance_direction-storyboard_scene-pd_session_1_pd_artifact_1_sc02',
      ),
    ).toHaveTextContent('sc02');

    fireEvent.change(input, { target: { value: 'Use character @chacto' } });
    expect(
      await screen.findByTestId('meeting-mention-option-registry-character_training-character_package-chacto_hero_pkg'),
    ).toHaveTextContent('Chacto Hero');
    expect(screen.getByTestId('meeting-mention-option-registry-character_training-character_card-card_chacto')).toHaveTextContent(
      'Chacto Persona',
    );
    expect(
      vi.mocked(global.fetch).mock.calls.some(([calledUrl]) =>
        String(calledUrl).includes('/api/v1/capabilities/performance_direction/sessions'),
      ),
    ).toBe(false);
    expect(
      vi.mocked(global.fetch).mock.calls.some(([calledUrl]) =>
        String(calledUrl).includes('/api/v1/capabilities/character_training/'),
      ),
    ).toBe(false);
  });

  it('offers registry-backed object completion results in the command bar', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    const input = screen.getByLabelText('Meeting instruction');
    fireEvent.change(input, { target: { value: 'Patch @registry' } });

    const option = await screen.findByTestId(
      'meeting-mention-option-registry-performance_direction-storyboard_scene-pd_session_registry_latest_sc03',
    );
    expect(option).toHaveTextContent('Registry storyboard / sc03');

    fireEvent.mouseDown(option);
    expect(input).toHaveValue('Patch @storyboard_scene:pd_session_registry:latest:sc03 ');
  });

  it('dispatches selected mention targets as structured meeting references', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    const input = screen.getByLabelText('Meeting instruction');
    fireEvent.change(input, {
      target: { value: 'Generate generic asset @fixture' },
    });
    fireEvent.mouseDown(
      await screen.findByTestId('meeting-mention-option-registry-fixture_pack-storyboard-fx_session_1'),
    );

    fireEvent.change(input, { target: { value: `${(input as HTMLInputElement).value}@fx_scene` } });
    fireEvent.mouseDown(
      await screen.findByTestId(
        'meeting-mention-option-registry-fixture_pack-storyboard_scene-fx_session_1_fx_artifact_1_fx_scene',
      ),
    );

    fireEvent.change(input, { target: { value: `${(input as HTMLInputElement).value}@fixture_character` } });
    fireEvent.mouseDown(
      await screen.findByTestId('meeting-mention-option-registry-fixture_pack-character_package-fixture_character_pkg'),
    );

    fireEvent.change(input, { target: { value: `${(input as HTMLInputElement).value}@fixture_character_card` } });
    fireEvent.mouseDown(
      await screen.findByTestId('meeting-mention-option-registry-fixture_pack-character_card-fixture_character_card'),
    );

    fireEvent.click(screen.getByLabelText('Send meeting instruction'));

    await screen.findByText(/exec-invoked/);
    const chatCall = vi.mocked(global.fetch).mock.calls.find(([url]) => String(url).includes('/chat'));
    expect(chatCall).toBeUndefined();

    const invokeCall = vi.mocked(global.fetch).mock.calls.find(([url]) =>
      String(url).includes('/object-actions/invoke'),
    );
    const body = JSON.parse(String(invokeCall?.[1]?.body || '{}'));
    expect(body.meeting_id).toBe('mtg_global');
    expect(body.thread_id).toBe('mtg_global');
    expect(body.object_action_plan).toEqual(
      expect.objectContaining({
        status: 'planned',
        request_plan: expect.objectContaining({
          steps: ['load_source_reference', 'patch_storyboard_scene'],
        }),
      }),
    );
    expect(body.entries).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: 'source',
          ref: expect.objectContaining({
            uri: 'mindscape://ig/reference/ref_global',
            object_kind: 'reference',
          }),
        }),
        expect.objectContaining({
          role: 'target',
          ref: expect.objectContaining({
            uri: 'mindscape://fixture_pack/storyboard_scene/fx_session_1:fx_artifact_1:fx_scene',
            object_kind: 'storyboard_scene',
          }),
        }),
        expect.objectContaining({
          role: 'character',
          ref: expect.objectContaining({
            uri: 'mindscape://fixture_pack/character_package/fixture_character_pkg',
            object_kind: 'character_package',
          }),
        }),
        expect.objectContaining({
          role: 'character',
          ref: expect.objectContaining({
            uri: 'mindscape://fixture_pack/character_card/fixture_character_card',
            object_kind: 'character_card',
          }),
        }),
      ]),
    );

    const planCall = vi.mocked(global.fetch).mock.calls.find(([url]) =>
      String(url).includes('/object-actions/plan'),
    );
    const planBody = JSON.parse(String(planCall?.[1]?.body || '{}'));
    expect(planBody.entries).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: 'source' }),
        expect.objectContaining({ role: 'target' }),
        expect.objectContaining({ role: 'character' }),
      ]),
    );
  });

  it('does not synthesize pack-owned object refs from unresolved raw mention tokens', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('Meeting instruction'), {
      target: {
        value:
          'Send asset @pack:visual_audit @storyboard:pd_manual @storyboard_scene:pd_manual:artifact_manual:sc09 @storyboard_proposal:pd_manual:proposal_01 @character:manual_pkg @character_card:manual_card',
      },
    });
    fireEvent.click(screen.getByLabelText('Send meeting instruction'));

    await screen.findByText('Task ID: task-accepted');
    const chatCall = vi.mocked(global.fetch).mock.calls.find(([url]) => String(url).includes('/chat'));
    expect(chatCall).toBeDefined();
    const chatBody = JSON.parse(String(chatCall?.[1]?.body || '{}'));
    expect(chatBody.action_params.object_action_entries).toEqual([
      expect.objectContaining({
        role: 'source',
        ref: expect.objectContaining({
          uri: 'mindscape://ig/reference/ref_global',
          object_kind: 'reference',
        }),
      }),
    ]);
    expect(chatBody.action_params.target_storyboards).toEqual([]);
    expect(chatBody.action_params.target_storyboard_scenes).toEqual([]);
    expect(chatBody.action_params.character_refs).toEqual([]);
    expect(JSON.stringify(chatBody.action_params.object_action_entries)).not.toContain('performance_direction');
    expect(JSON.stringify(chatBody.action_params.object_action_entries)).not.toContain('character_training');
    expect(
      vi.mocked(global.fetch).mock.calls.some(([url]) => String(url).includes('/object-actions/plan')),
    ).toBe(false);
    expect(
      vi.mocked(global.fetch).mock.calls.some(([url]) => String(url).includes('/object-actions/invoke')),
    ).toBe(false);
  });

  it('switches the graph canvas to another meeting session from the session strip', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId('meeting-sessions-toggle'));
    fireEvent.click(await screen.findByTestId('meeting-session-card-mtg_other'));

    await waitFor(() => {
      expect(screen.queryByTestId('meeting-sessions-popover')).toBeNull();
      expect(screen.getByTestId('meeting-graph-node-root')).toHaveTextContent('mtg_other');
    });
  });

  it('adds a command as a task node, dispatches it, and opens the scoped console', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Meeting instruction'), {
      target: { value: 'Analyze this reference' },
    });
    fireEvent.click(screen.getByLabelText('Send meeting instruction'));

    expect(screen.getByText('Analyze this reference')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-console-drawer')).toBeInTheDocument();
    expect(await screen.findByText('Task ID: task-accepted')).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      'http://api.test/api/v1/workspaces/ws-global/chat',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"thread_id":"mtg_global"'),
      }),
    );
  });

  it('dispatches a selected pack tool target through the meeting thread', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'ig / Visual Audit' })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId('meeting-pack-tool-select'), {
      target: { value: 'visual_audit' },
    });
    fireEvent.change(screen.getByLabelText('Meeting instruction'), {
      target: { value: 'Prepare the visual reference set' },
    });
    fireEvent.click(screen.getByLabelText('Send meeting instruction'));

    await screen.findByText('Task ID: task-accepted');
    const chatCall = vi.mocked(global.fetch).mock.calls.find(([url]) => String(url).includes('/chat'));
    expect(chatCall?.[1]).toEqual(
      expect.objectContaining({
        body: expect.stringContaining('"action":"execute_playbook"'),
      }),
    );
    expect(chatCall?.[1]).toEqual(
      expect.objectContaining({
        body: expect.stringContaining('"playbook_code":"visual_audit"'),
      }),
    );
    expect(chatCall?.[1]).toEqual(
      expect.objectContaining({
        body: expect.stringContaining('"thread_id":"mtg_global"'),
      }),
    );
  });
});
