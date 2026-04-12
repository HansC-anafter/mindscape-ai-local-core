'use client';

import React, { useMemo } from 'react';
import { AlertCircle, Briefcase, CheckCircle2, RefreshCw, Shield, Upload } from 'lucide-react';

import { useConnectedAccounts } from './accounts/hooks/useConnectedAccounts';

interface ManagedAccountsPanelProps {
  workspaceId: string;
  apiUrl: string;
  onOpenAccess: () => void;
  onOpenPublish: () => void;
}

export default function ManagedAccountsPanel(props: ManagedAccountsPanelProps) {
  const { workspaceId, apiUrl, onOpenAccess, onOpenPublish } = props;
  const { connectedAccounts, refresh } = useConnectedAccounts({ apiUrl, workspaceId });

  const summary = useMemo(() => {
    const activeCount = connectedAccounts.filter((account) => account.status === 'connected').length;
    const attentionCount = connectedAccounts.filter((account) => account.status !== 'connected').length;
    return {
      total: connectedAccounts.length,
      activeCount,
      attentionCount,
    };
  }, [connectedAccounts]);

  return (
    <div className="h-full flex flex-col p-4">
      <div className="mb-4 rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Managed Accounts</h2>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
              Workspace-owned or client channels used for publishing and sync. Separate from discovery seeds and targets.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              void refresh();
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700/50"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 dark:border-emerald-900/60 dark:bg-emerald-900/20">
            <div className="text-xs uppercase tracking-wide text-emerald-700 dark:text-emerald-300">Connected</div>
            <div className="mt-1 text-2xl font-semibold text-emerald-900 dark:text-emerald-100">{summary.activeCount}</div>
          </div>
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 dark:border-amber-900/60 dark:bg-amber-900/20">
            <div className="text-xs uppercase tracking-wide text-amber-700 dark:text-amber-300">Needs Attention</div>
            <div className="mt-1 text-2xl font-semibold text-amber-900 dark:text-amber-100">{summary.attentionCount}</div>
          </div>
          <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-3 dark:border-blue-900/60 dark:bg-blue-900/20">
            <div className="text-xs uppercase tracking-wide text-blue-700 dark:text-blue-300">Total Managed</div>
            <div className="mt-1 text-2xl font-semibold text-blue-900 dark:text-blue-100">{summary.total}</div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onOpenAccess}
            className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-3 py-2 text-xs font-medium text-white hover:bg-violet-700"
          >
            <Shield className="h-3.5 w-3.5" />
            Open Access
          </button>
          <button
            type="button"
            onClick={onOpenPublish}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700/50"
          >
            <Upload className="h-3.5 w-3.5" />
            Open Publish
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3">
        {connectedAccounts.length === 0 ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/60 dark:bg-amber-900/20">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 text-amber-600 dark:text-amber-400" />
              <div>
                <div className="text-sm font-semibold text-amber-900 dark:text-amber-100">No managed IG channels yet</div>
                <p className="mt-1 text-sm text-amber-800 dark:text-amber-200">
                  Connect an Instagram channel in Access → OAuth before using publish or content sync flows.
                </p>
              </div>
            </div>
          </div>
        ) : (
          connectedAccounts.map((account) => {
            const isConnected = account.status === 'connected';
            return (
              <div
                key={account.channel_config_id}
                className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Briefcase className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                      <h3 className="truncate text-base font-semibold text-gray-900 dark:text-gray-100">
                        {account.channel_name}
                      </h3>
                    </div>
                    <div className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                      {account.username ? `@${account.username}` : 'Instagram channel binding'}
                    </div>
                    <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      channel_config_id: <span className="font-mono">{account.channel_config_id}</span>
                    </div>
                  </div>

                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                      isConnected
                        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300'
                        : 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
                    }`}
                  >
                    {isConnected ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
                    {isConnected ? 'Ready for publish/sync' : 'Reconnect needed'}
                  </span>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-gray-900/40 dark:text-gray-300">
                    Use this area for accounts you actively operate for your brand or clients.
                  </div>
                  <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-gray-900/40 dark:text-gray-300">
                    Discovery targets and crawled handles stay in Discovery and do not appear here by default.
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
