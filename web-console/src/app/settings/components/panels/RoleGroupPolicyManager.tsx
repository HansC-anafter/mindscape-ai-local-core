'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';

interface RoleGroupPolicyManagerProps {
  rolePolicies: Record<string, string[]>;
  onChange: (rolePolicies: Record<string, string[]>) => void;
}

const PERMISSION_OPTIONS = ['read', 'write', 'publish', '*'];

export function RoleGroupPolicyManager({
  rolePolicies,
  onChange,
}: RoleGroupPolicyManagerProps) {
  const [newRole, setNewRole] = useState('');

  const handleAddRole = () => {
    if (newRole.trim() && !rolePolicies[newRole.trim()]) {
      onChange({
        ...rolePolicies,
        [newRole.trim()]: ['read'],
      });
      setNewRole('');
    }
  };

  const handleTogglePermission = (role: string, permission: string) => {
    const currentPermissions = rolePolicies[role] || [];
    let newPermissions: string[];

    if (permission === '*') {
      newPermissions = currentPermissions.includes('*') ? [] : ['*'];
    } else {
      if (currentPermissions.includes('*')) {
        newPermissions = [permission];
      } else {
        newPermissions = currentPermissions.includes(permission)
          ? currentPermissions.filter((p) => p !== permission)
          : [...currentPermissions, permission];
      }
    }

    onChange({
      ...rolePolicies,
      [role]: newPermissions,
    });
  };

  const handleRemoveRole = (role: string) => {
    const newPolicies = { ...rolePolicies };
    delete newPolicies[role];
    onChange(newPolicies);
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="mb-3">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
          {t('rolePolicies')}
        </h4>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {t('rolePoliciesDescription')}
        </p>
      </div>

      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={newRole}
          onChange={(e) => setNewRole(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleAddRole()}
          placeholder={t('enterRoleName')}
          className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
        />
        <button
          type="button"
          onClick={handleAddRole}
          className="px-3 py-2 text-sm bg-accent dark:bg-blue-700 text-white rounded hover:bg-accent/90 dark:hover:bg-blue-600 transition-colors"
        >
          {t('add')}
        </button>
      </div>

      {Object.keys(rolePolicies).length > 0 ? (
        <div className="space-y-3">
          {Object.entries(rolePolicies).map(([role, permissions]) => (
            <div
              key={role}
              className="border border-gray-200 dark:border-gray-700 rounded p-3"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {role}
                </span>
                <button
                  type="button"
                  onClick={() => handleRemoveRole(role)}
                  className="text-xs text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                >
                  {t('remove')}
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {PERMISSION_OPTIONS.map((permission) => (
                  <label
                    key={permission}
                    className={`flex items-center gap-1 px-2 py-1 rounded text-xs cursor-pointer transition-colors ${
                      permissions.includes(permission)
                        ? 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300'
                        : 'bg-surface-accent dark:bg-gray-700 text-primary dark:text-gray-300 hover:bg-surface-secondary dark:hover:bg-gray-600'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={permissions.includes(permission)}
                      onChange={() => handleTogglePermission(role, permission)}
                      className="rounded"
                    />
                    <span>{permission}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-500 dark:text-gray-400 italic">
          {t('noRolePoliciesConfigured')}
        </p>
      )}
    </div>
  );
}

