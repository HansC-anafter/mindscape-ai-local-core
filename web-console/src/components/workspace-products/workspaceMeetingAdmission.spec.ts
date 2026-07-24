import { describe, expect, it } from 'vitest';

import type { WorkspaceCapabilitySetSnapshot } from '@/lib/workspace-product-configuration-api';
import { resolveMeetingProductAdmission } from './workspaceMeetingAdmission';

function snapshot(): WorkspaceCapabilitySetSnapshot {
  return {
    source_runtime_id: 'runtime-one',
    workspace_id: 'ws-one',
    explicit_active_group_id: 'group-one',
    topology_revision: 7,
    catalog_hash: 'a'.repeat(64),
    snapshot_hash: 'b'.repeat(64),
    workspace_scope_revision: 2,
    group_scope_revision: 1,
    workspace_admission_mode: 'enforced',
    editable_scopes: ['workspace'],
    scope_configurations: [],
    available_products: [{
      pcs_id: 'instagram_workspace_intelligence',
      exact_version: '1.0.0',
      display_name: 'Instagram',
      outcome_summary: 'References',
      surface_ids: ['instagram.workspace.references'],
      product_surfaces: [{
        id: 'instagram.workspace.references',
        display_name: 'Instagram References',
        selectors: {
          api_prefixes: ['/api/v1/ig'],
          tool_prefixes: ['ig.'],
          tool_keys: [],
          playbook_codes: [],
          ui_routes: ['/workspaces/{workspace_id}/capability-ui-hosts/ig'],
        },
      }],
      closure_summary: {
        total_packs: 1,
        exact_ready_packs: 1,
        missing_packs: 0,
        disabled_packs: 0,
        version_mismatch_packs: 0,
      },
      pack_closure: [{
        provider: 'mindscape-cloud',
        code: 'ig',
        version: '1.0.195',
        readiness: 'ready',
      }],
    }],
    effective_assignments: [{
      pcs_id: 'instagram_workspace_intelligence',
      pcs_version: '1.0.0',
      product_surface_ids: ['instagram.workspace.references'],
      configuration_sources: ['workspace'],
      host_ready: true,
    }],
    configuration_errors: [],
  };
}

describe('resolveMeetingProductAdmission', () => {
  it('derives an exact Meeting root selector from the assigned product surface', () => {
    expect(resolveMeetingProductAdmission({
      snapshot: snapshot(),
      workspaceId: 'ws-one',
      capabilityCode: 'ig',
      surfaceRoute: '/workspaces/ws-one/capability-ui-hosts/ig/references?tab=shared',
    })).toEqual({
      active_group_id: 'group-one',
      observed_topology_revision: 7,
      product_surface_id: 'instagram.workspace.references',
      product_selector_kind: 'api_prefix',
      product_selector_key: '/api/v1/ig',
      operation_type: 'generate',
      execution_backend: 'local',
    });
  });

  it('fails closed when the active capability has no assigned catalog surface', () => {
    expect(resolveMeetingProductAdmission({
      snapshot: snapshot(),
      workspaceId: 'ws-one',
      capabilityCode: 'yogacoach',
      surfaceRoute: '/workspaces/ws-one/capability-ui-hosts/yogacoach/live-practice',
    })).toBeNull();
  });
});
