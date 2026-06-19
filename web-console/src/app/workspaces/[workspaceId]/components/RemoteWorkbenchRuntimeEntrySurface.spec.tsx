import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RemoteWorkbenchRuntimeEntrySurface } from './RemoteWorkbenchRuntimeEntrySurface';
import {
  buildRemoteWorkbenchGraphAnchor,
  buildRemoteWorkbenchMeetingId,
} from './remoteWorkbenchRuntimeEntryModel';

vi.mock('@/components/capabilities/meeting-workbench/runs/useHostRuntimeRunSession', () => ({
  useHostRuntimeRunSession: ({ workspaceId, meetingId, selectedObjectRef }: any) => ({
    status: { enabled: true, total_bridges: 1, runtime_surfaces: ['codex_cli'], bridges: [] },
    session: {
      id: 'session-remote',
      execution_id: 'exec-remote',
      workspace_id: workspaceId,
      runtime_surface: 'codex_cli',
      runtime_id: 'codex_cli',
      status: 'ready',
      cwd: '/workspace',
      last_event_seq: 0,
    },
    events: [],
    bridgeService: null,
    isStarting: false,
    isStartingBridge: false,
    error: null,
    lastSeq: 0,
    graphContext: {
      context_contract_version: 'aol_graph_context_v1',
      source: 'aol_domain_object_graph_runtime_runs',
      meeting_id: meetingId,
      selected_graph_anchor: selectedObjectRef
        ? {
            anchor_uri: selectedObjectRef.uri,
            ref: selectedObjectRef,
            owner_pack: selectedObjectRef.owner_pack,
            object_kind: selectedObjectRef.object_kind,
            object_id: selectedObjectRef.object_id,
          }
        : null,
      graph_selection_ref: {
        kind: 'GraphSelection',
        workspace_id: workspaceId,
        meeting_id: meetingId,
        anchor_uri: selectedObjectRef?.uri ?? null,
        selected_ref_uris: selectedObjectRef ? [selectedObjectRef.uri] : [],
        selection_hash: 'gsel_remote_test',
        selector_scope: selectedObjectRef ? 'anchored_object_neighborhood' : 'workspace_meeting',
        status: selectedObjectRef ? 'anchored' : 'empty_anchor',
      },
      graph_context_ref: {
        kind: 'SubgraphContext',
        context_id: 'gctx_remote_test',
        workspace_id: workspaceId,
        meeting_id: meetingId,
        graph_selection_hash: 'gsel_remote_test',
      },
      graph_snapshot_summary: {
        snapshot_hash: 'ogau_remote_test',
        node_count: selectedObjectRef ? 1 : 0,
        edge_count: 0,
        owner_packs: selectedObjectRef ? [selectedObjectRef.owner_pack] : [],
        truncated: false,
        budget: { max_nodes: 16, max_edges: 32, max_prompt_chars: 4000 },
        provenance_refs: selectedObjectRef ? [`selected_graph_anchor:${selectedObjectRef.uri}`] : ['selected_graph_anchor:none'],
      },
      object_graph_aggregate_unit_ref: {
        kind: 'ObjectGraphAggregateUnitRef',
        unit_id: 'ogau_remote_test',
        snapshot_hash: 'ogau_remote_test',
      },
      object_graph_aggregate_unit: {
        kind: 'ObjectGraphAggregateUnit',
        unit_id: 'ogau_remote_test',
        owner_pack: selectedObjectRef?.owner_pack ?? null,
        anchor_uri: selectedObjectRef?.uri ?? null,
        node_count: selectedObjectRef ? 1 : 0,
        edge_count: 0,
        budget: { max_nodes: 16, max_edges: 32, max_prompt_chars: 4000 },
        truncation: { truncated: false, reason: null },
        snapshot_hash: 'ogau_remote_test',
        provenance_refs: selectedObjectRef ? [`selected_graph_anchor:${selectedObjectRef.uri}`] : ['selected_graph_anchor:none'],
      },
      selected_object_ref: selectedObjectRef,
    },
    startBridge: () => undefined,
    submitPrompt: () => undefined,
  }),
}));

describe('RemoteWorkbenchRuntimeEntrySurface', () => {
  it('renders the RUNS composer, voice input, tool panels, and graph context for the remote target', () => {
    render(
      <RemoteWorkbenchRuntimeEntrySurface
        workspaceId="ws-test"
        targetCapabilityCode="ig"
        targetCapabilityLabel="Instagram Workbench"
        apiUrl="http://api.test"
      />,
    );

    expect(screen.getByTestId('remote-workbench-runtime-entry')).toBeInTheDocument();
    expect(screen.getByTestId('meeting-runs-workspace-surface')).toBeInTheDocument();
    expect(screen.getByTestId('agent-freeform-mobile-stack')).toBeInTheDocument();
    expect(screen.getByTestId('host-runtime-composer')).toBeInTheDocument();
    expect(screen.getByTestId('host-runtime-voice-prompt-button')).toBeInTheDocument();
    expect(screen.getByTestId('host-runtime-object-context')).toHaveTextContent('gsel_remote_test');
    expect(screen.getByTestId('agent-freeform-mobile-panel-tool_calls')).toBeInTheDocument();
  });
});

describe('remoteWorkbenchRuntimeEntryModel', () => {
  it('builds one deterministic meeting id and graph anchor for the target pack', () => {
    expect(buildRemoteWorkbenchMeetingId({
      workspaceId: 'ws-test',
      targetCapabilityCode: 'ig',
    })).toBe('remote-workbench:ws-test:ig');

    expect(buildRemoteWorkbenchGraphAnchor({
      workspaceId: 'ws-test',
      targetCapabilityCode: 'ig',
      targetCapabilityLabel: 'Instagram Workbench',
    })).toMatchObject({
      uri: 'aol://workspace/ws-test/capability/ig',
      owner_pack: 'ig',
      object_kind: 'capability_runtime_entry',
      object_id: 'ig',
      workspace_id: 'ws-test',
      source_surface: 'remote_workbench_runtime_entry',
    });
  });
});
