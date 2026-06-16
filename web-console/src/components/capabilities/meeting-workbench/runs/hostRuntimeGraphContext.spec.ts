import { describe, expect, it } from 'vitest';

import { buildHostRuntimeGraphContext } from './hostRuntimeGraphContext';

describe('buildHostRuntimeGraphContext', () => {
  it('builds a bounded GraphSelection and ObjectGraphAggregateUnit contract', () => {
    const context = buildHostRuntimeGraphContext({
      workspaceId: 'ws-test',
      meetingId: 'mtg-test',
      selectedObjectRef: {
        uri: 'aol://workspace/ws-test/ig/post/post-1',
        owner_pack: 'ig',
        object_kind: 'post',
        object_id: 'post-1',
        workspace_id: 'ws-test',
        selector: {
          account_id: 'acct-1',
        },
        source_surface: 'ig.assets',
      },
    });

    expect(context.context_contract_version).toBe('aol_graph_context_v1');
    expect(context.selected_graph_anchor?.anchor_uri).toBe('aol://workspace/ws-test/ig/post/post-1');
    expect(context.graph_selection_ref.kind).toBe('GraphSelection');
    expect(context.graph_selection_ref.selected_ref_uris).toEqual(['aol://workspace/ws-test/ig/post/post-1']);
    expect(context.graph_context_ref.kind).toBe('SubgraphContext');
    expect(context.object_graph_aggregate_unit.kind).toBe('ObjectGraphAggregateUnit');
    expect(context.object_graph_aggregate_unit.budget).toMatchObject({
      max_nodes: 16,
      max_edges: 32,
      max_prompt_chars: 4000,
    });
    expect(context.object_graph_aggregate_unit.truncation.truncated).toBe(false);
    expect(context.graph_snapshot_summary.snapshot_hash).toBe(context.object_graph_aggregate_unit.snapshot_hash);
  });

  it('keeps empty graph context bounded without starting side-effect work', () => {
    const context = buildHostRuntimeGraphContext({
      workspaceId: 'ws-test',
      meetingId: null,
      selectedObjectRef: null,
    });

    expect(context.selected_graph_anchor).toBeNull();
    expect(context.graph_selection_ref.status).toBe('empty_anchor');
    expect(context.graph_snapshot_summary.node_count).toBe(0);
    expect(context.graph_snapshot_summary.edge_count).toBe(0);
    expect(context.object_graph_aggregate_unit.provenance_refs).toEqual(['selected_graph_anchor:none']);
  });
});
