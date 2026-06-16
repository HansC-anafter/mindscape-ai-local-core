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
    expect(context.source).toBe('aol_domain_object_graph_runtime_runs');
    expect(context.selected_graph_anchor?.anchor_uri).toBe('aol://workspace/ws-test/ig/post/post-1');
    expect(context.graph_selection_ref.kind).toBe('GraphSelection');
    expect(context.graph_selection_ref.selected_ref_uris).toEqual(['aol://workspace/ws-test/ig/post/post-1']);
    expect(context.graph_selection_ref.lens_code).toBe('anchor_object_lens');
    expect(context.graph_context_ref.kind).toBe('SubgraphContext');
    expect(context.object_graph_aggregate_unit.kind).toBe('ObjectGraphAggregateUnit');
    expect(context.object_graph_aggregate_unit_ref.unit_id).toBe(context.object_graph_aggregate_unit.unit_id);
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

  it('uses pack-provided GraphSelection lens metadata when available', () => {
    const context = buildHostRuntimeGraphContext({
      workspaceId: 'ws-test',
      meetingId: 'mtg-test',
      selectedObjectRef: null,
      graphSelection: {
        owner_pack: 'ig',
        selection_kind: 'anchor',
        lens_code: 'reference_curation_lens',
        relation_scope: ['authored_by_account', 'part_of_post'],
        node_limit: 24,
        relation_limit: 32,
        snapshot_budget: {
          max_nodes: 16,
          max_edges: 32,
          max_prompt_chars: 4000,
        },
        source_surface: 'ig.references_grid',
        governance_tags: ['bounded_reference_set'],
        selection_hash: 'ig_gsel_test',
        anchors: [{
          uri: 'mindscape://ig/reference/ref-1?workspace=ws-test',
          owner_pack: 'ig',
          object_kind: 'reference',
          object_id: 'ref-1',
          workspace_id: 'ws-test',
          source_surface: 'ig.references_grid',
        }],
      },
    });

    expect(context.selected_graph_anchor?.anchor_uri).toBe('mindscape://ig/reference/ref-1?workspace=ws-test');
    expect(context.graph_selection_ref.selection_hash).toBe('ig_gsel_test');
    expect(context.graph_selection_ref.lens_code).toBe('reference_curation_lens');
    expect(context.graph_selection_ref.relation_scope).toEqual(['authored_by_account', 'part_of_post']);
    expect(context.graph_snapshot_summary.node_count).toBe(1);
    expect(context.selected_object_ref?.object_kind).toBe('reference');
  });
});
