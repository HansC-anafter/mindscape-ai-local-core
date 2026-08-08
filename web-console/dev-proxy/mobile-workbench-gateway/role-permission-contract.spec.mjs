import assert from 'node:assert/strict';
import test from 'node:test';

import {
  normalizeRolePermissionFields,
  permissionsForRole,
} from './role-permission-contract.mjs';
import {
  requiredWorkspacePermission,
} from './workspace-permission-rules.mjs';

function malformed(reason) {
  throw new Error(reason);
}

test('role permission projection requires the exact immutable role expansion', () => {
  const permissions = [...permissionsForRole('workspace_editor')].sort();
  assert.deepEqual(
    normalizeRolePermissionFields({
      role_keys: ['workspace_editor'],
      permissions,
    }, malformed),
    {
      roleKeys: ['workspace_editor'],
      permissions,
    },
  );
  assert.throws(
    () => normalizeRolePermissionFields({
      role_keys: ['workspace_editor'],
      permissions: ['workspace.read'],
    }, malformed),
    /effective_role_permission_projection_mismatch/,
  );
});

test('gateway maps fixed reads and capability actions to explicit permissions', () => {
  assert.equal(
    requiredWorkspacePermission({
      isBootAsset: false,
      capabilityCode: null,
      path: '/api/v1/workspaces/ws/tasks',
    }, 'GET'),
    'workspace.read',
  );
  assert.equal(
    requiredWorkspacePermission({
      isBootAsset: false,
      capabilityCode: 'ig',
      path: '/api/v1/capabilities/ig/run',
    }, 'POST'),
    'workspace.execute',
  );
  assert.equal(
    requiredWorkspacePermission({
      isBootAsset: false,
      capabilityCode: null,
      path: '/api/v1/workspaces/ws/tasks',
    }, 'POST'),
    'workspace.read',
  );
  assert.equal(
    requiredWorkspacePermission({
      isBootAsset: false,
      capabilityCode: null,
      path: '/api/v1/workspaces/ws/device-bindings/device/media-sessions',
    }, 'POST'),
    'workspace.execute',
  );
});
