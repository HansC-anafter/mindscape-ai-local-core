'use client';

import React, { useEffect, useState } from 'react';
import { Globe2, RefreshCw, SlidersHorizontal } from 'lucide-react';
import { useT } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';

interface BackendModeSettingsProps {
  mode: string;
  onModeChange: (mode: string) => void;
}

interface ResourceGovernanceContext {
  mode?: string;
  scope?: string;
  is_global_admin?: boolean;
  user_id?: string;
  tenant_id?: string;
  workspace_id?: string | null;
  workspace_ids?: string[];
  can_manage_global?: boolean;
  can_manage_workspace_allocations?: boolean;
}

export function BackendModeSettings({ mode }: BackendModeSettingsProps) {
  const t = useT();
  const [context, setContext] = useState<ResourceGovernanceContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadContext = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await settingsApi.get<ResourceGovernanceContext>('/api/v1/resource-governance/context');
      setContext(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load resource governance context');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadContext();
  }, []);

  const globalActive = Boolean(context?.is_global_admin && context?.mode === 'global');
  const workspaceActive = Boolean(context?.mode === 'workspace');

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('resourceGovernance' as any)}
          </label>
          <div className="mt-1 text-xs text-secondary dark:text-gray-400">
            Agent runtime mode: {mode || 'local'}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void loadContext()}
          disabled={loading}
          className="inline-flex h-8 items-center gap-2 rounded-md border border-default px-2 text-xs font-medium text-primary hover:bg-surface-secondary disabled:opacity-50 dark:border-gray-700 dark:text-gray-100 dark:hover:bg-gray-800"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Refresh
        </button>
      </div>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <a
          href="/settings?tab=runtime&section=host-resources"
          className={`rounded-md border p-4 text-left transition-colors ${
            globalActive
              ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30'
              : 'border-default hover:bg-surface-secondary dark:border-gray-700 dark:hover:bg-gray-800'
          }`}
        >
          <div className="flex items-center gap-2 text-sm font-semibold text-primary dark:text-gray-100">
            <Globe2 className="h-4 w-4 text-secondary dark:text-gray-400" aria-hidden="true" />
            Global Control
          </div>
          <div className="mt-2 text-xs text-secondary dark:text-gray-400">
            {context?.can_manage_global ? 'Available to this user' : 'Global admin required'}
          </div>
        </a>
        <a
          href="/settings?tab=runtime&section=workspace-resource-allocations"
          className={`rounded-md border p-4 text-left transition-colors ${
            workspaceActive
              ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30'
              : 'border-default hover:bg-surface-secondary dark:border-gray-700 dark:hover:bg-gray-800'
          }`}
        >
          <div className="flex items-center gap-2 text-sm font-semibold text-primary dark:text-gray-100">
            <SlidersHorizontal className="h-4 w-4 text-secondary dark:text-gray-400" aria-hidden="true" />
            Workspace Scope
          </div>
          <div className="mt-2 text-xs text-secondary dark:text-gray-400">
            {context?.workspace_id || `${context?.workspace_ids?.length || 0} accessible workspace(s)`}
          </div>
        </a>
      </div>
    </div>
  );
}
