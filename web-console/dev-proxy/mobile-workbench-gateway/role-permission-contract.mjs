const ROLE_PERMISSIONS = new Map([
  ['local_core_super_admin', new Set([
    'local_core.settings.manage',
    'local_core.workspaces.create',
    'local_core.access.manage',
    'workspace.read',
    'workspace.content.write',
    'workspace.execute',
    'workspace.settings.manage',
    'workspace.members.manage',
    'workspace.audit.read',
    'workspace.owner.manage',
    'workspace.delete',
  ])],
  ['workspace_owner', new Set([
    'workspace.read',
    'workspace.content.write',
    'workspace.execute',
    'workspace.settings.manage',
    'workspace.members.manage',
    'workspace.audit.read',
    'workspace.owner.manage',
    'workspace.delete',
  ])],
  ['workspace_admin', new Set([
    'workspace.read',
    'workspace.content.write',
    'workspace.execute',
    'workspace.settings.manage',
    'workspace.members.manage',
    'workspace.audit.read',
  ])],
  ['workspace_editor', new Set([
    'workspace.read',
    'workspace.content.write',
    'workspace.execute',
  ])],
  ['workspace_viewer', new Set(['workspace.read'])],
]);

function normalizedStringList(values, { maxItems, malformed, reason }) {
  if (!Array.isArray(values) || values.length < 1 || values.length > maxItems) {
    malformed(reason);
  }
  const normalized = values.map((value) => {
    if (typeof value !== 'string' || !value || value !== value.trim()) {
      malformed(reason);
    }
    return value;
  });
  if (new Set(normalized).size !== normalized.length) {
    malformed(reason);
  }
  return normalized.sort();
}

export function normalizeRolePermissionFields(row, malformed) {
  const roleKeys = normalizedStringList(row.role_keys, {
    maxItems: 2,
    malformed,
    reason: 'invalid_effective_role_keys',
  });
  const expectedPermissions = new Set();
  for (const roleKey of roleKeys) {
    const rolePermissions = ROLE_PERMISSIONS.get(roleKey);
    if (!rolePermissions) {
      malformed('invalid_effective_role_key');
    }
    for (const permission of rolePermissions) {
      expectedPermissions.add(permission);
    }
  }
  const permissions = normalizedStringList(row.permissions, {
    maxItems: 11,
    malformed,
    reason: 'invalid_effective_permissions',
  });
  if (
    permissions.length !== expectedPermissions.size
    || permissions.some((permission) => !expectedPermissions.has(permission))
  ) {
    malformed('effective_role_permission_projection_mismatch');
  }
  return { roleKeys, permissions };
}

export function permissionsForRole(roleKey) {
  return new Set(ROLE_PERMISSIONS.get(roleKey) || []);
}
