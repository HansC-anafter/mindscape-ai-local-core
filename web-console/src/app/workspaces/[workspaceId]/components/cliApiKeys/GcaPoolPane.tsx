'use client';

import { parseServerTimestamp } from '@/lib/time';

import { formatServerDateTime, formatTimeRemaining } from './helpers';
import type {
  PoolAccount,
  WorkspaceGcaStatus,
} from './types';

interface GcaPoolPaneProps {
  addingAccount: boolean;
  boundGcaRuntimeId: string;
  executorRuntimeId: string | null;
  pendingRuntimeId: string | null;
  poolAccounts: PoolAccount[];
  savedBinding: boolean;
  savingBinding: boolean;
  workspaceGcaStatus: WorkspaceGcaStatus | null;
  workspaceId?: string;
  onAddAccount: () => void | Promise<void>;
  onBoundGcaRuntimeIdChange: (runtimeId: string) => void;
  onConnectAccount: (runtimeId: string) => void | Promise<void>;
  onRemoveAccount: (runtimeId: string) => void | Promise<void>;
  onSaveWorkspaceBinding: (runtimeId: string) => Promise<boolean>;
  onToggleEnabled: (runtimeId: string, enabled: boolean) => void | Promise<void>;
}

export function GcaPoolPane({
  addingAccount,
  boundGcaRuntimeId,
  executorRuntimeId,
  pendingRuntimeId,
  poolAccounts,
  savedBinding,
  savingBinding,
  workspaceGcaStatus,
  workspaceId,
  onAddAccount,
  onBoundGcaRuntimeIdChange,
  onConnectAccount,
  onRemoveAccount,
  onSaveWorkspaceBinding,
  onToggleEnabled,
}: GcaPoolPaneProps) {
  return (
    <>
      <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg p-3">
        <p className="text-xs font-medium text-emerald-700 dark:text-emerald-300 mb-1">
          GCA Multi-Account Pool
        </p>
        <p className="text-xs text-emerald-600 dark:text-emerald-400">
          Add multiple Google accounts for automatic rotation. Workspace status below reflects backend pool
          selection and cooldown resets after observed 429s; it does not read the external IDE quota dashboard directly.
        </p>
      </div>

      {workspaceId && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 space-y-2">
          <p className="text-xs font-medium text-blue-700 dark:text-blue-300">Workspace GCA policy</p>
          <p className="text-xs text-blue-600 dark:text-blue-400">
            By default, this workspace uses the enabled GCA pool with automatic rotation. Only pick a specific
            account if you want to pin this workspace to one runtime for debugging or cost isolation. Discoverable
            workspaces without their own override can fall back to the initiating or dispatch workspace, with trace
            metadata recorded per task.
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={boundGcaRuntimeId}
              onChange={async (event) => {
                const nextValue = event.target.value;
                const previousValue = boundGcaRuntimeId;
                onBoundGcaRuntimeIdChange(nextValue);
                const ok = await onSaveWorkspaceBinding(nextValue);
                if (!ok) {
                  onBoundGcaRuntimeIdChange(previousValue);
                }
              }}
              disabled={!executorRuntimeId || savingBinding}
              className="min-w-[220px] px-2 py-1.5 text-xs rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="">Use enabled pool rotation</option>
              {poolAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  Pin to {account.email || account.id} ({account.id})
                </option>
              ))}
            </select>
            <span className="text-[11px] text-gray-500 dark:text-gray-400">
              Executor: {executorRuntimeId || 'not bound'}
              {workspaceGcaStatus?.policy_mode === 'pinned_runtime'
                ? ` · saved: pinned ${workspaceGcaStatus.preferred_runtime_id || 'unknown'}`
                : workspaceGcaStatus
                  ? ' · saved: rotation enabled'
                  : ''}
            </span>
            {savingBinding && (
              <span className="text-[11px] px-2 py-1 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">
                Saving...
              </span>
            )}
            {!savingBinding && savedBinding && (
              <span className="text-[11px] px-2 py-1 rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">
                Saved
              </span>
            )}
          </div>
          {workspaceGcaStatus && (
            <div
              className={`rounded-md border p-2 text-[11px] ${
                workspaceGcaStatus.error
                  ? 'border-amber-200 dark:border-amber-800 bg-amber-50/60 dark:bg-amber-900/10 text-amber-700 dark:text-amber-300'
                  : 'border-blue-200 dark:border-blue-800 bg-white/70 dark:bg-gray-900/20 text-blue-700 dark:text-blue-300'
              }`}
            >
              <div className="font-medium">Backend pool resolution</div>
              <div className="mt-1">
                Policy:{' '}
                {workspaceGcaStatus.policy_mode === 'pinned_runtime'
                  ? `Pinned to ${workspaceGcaStatus.preferred_runtime_id || 'unknown'}`
                  : 'Enabled pool rotation'}
              </div>
              <div>
                Selected now:{' '}
                {workspaceGcaStatus.resolved_runtime_id
                  ? `${workspaceGcaStatus.resolved_email || workspaceGcaStatus.resolved_runtime_id} (${workspaceGcaStatus.resolved_runtime_id})`
                  : 'No eligible account'}
              </div>
              <div>
                Status: {workspaceGcaStatus.resolved_status}
                {workspaceGcaStatus.cooldown_until
                  ? ` · resets ${formatServerDateTime(workspaceGcaStatus.cooldown_until)} (${formatTimeRemaining(workspaceGcaStatus.cooldown_until)})`
                  : ''}
              </div>
              <div>
                Pool health: {workspaceGcaStatus.available_count} available / {workspaceGcaStatus.cooling_count}{' '}
                cooling / {workspaceGcaStatus.pool_count} total
                {workspaceGcaStatus.next_reset_at
                  ? ` · next reset ${formatServerDateTime(workspaceGcaStatus.next_reset_at)} (${formatTimeRemaining(workspaceGcaStatus.next_reset_at)})`
                  : ''}
              </div>
              <div>
                Resolution: {workspaceGcaStatus.selection_reason}
                {workspaceGcaStatus.effective_workspace_id && workspaceGcaStatus.effective_workspace_id !== workspaceId
                  ? ` · effective workspace ${workspaceGcaStatus.effective_workspace_id}`
                  : ''}
              </div>
              {workspaceGcaStatus.error && <div className="mt-1">{workspaceGcaStatus.error}</div>}
            </div>
          )}
        </div>
      )}

      <div className="space-y-2">
        {poolAccounts.length === 0 && !addingAccount && (
          <p className="text-xs text-gray-500 dark:text-gray-400 py-2">
            No accounts in pool. Add a Google account to get started.
          </p>
        )}
        {poolAccounts.map((account) => {
          const isCooling =
            account.cooldown_until &&
            (parseServerTimestamp(account.cooldown_until)?.getTime() ?? 0) > Date.now();
          const isPending = pendingRuntimeId === account.id;

          return (
            <div
              key={account.id}
              className={`flex items-center gap-3 p-2.5 rounded-lg border transition-colors ${
                !account.pool_enabled
                  ? 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 opacity-60'
                  : isCooling
                    ? 'border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-900/10'
                    : account.auth_status === 'connected'
                      ? 'border-green-200 dark:border-green-800 bg-green-50/30 dark:bg-green-900/10'
                      : 'border-gray-200 dark:border-gray-700'
              }`}
            >
              <span
                className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                  isPending
                    ? 'bg-amber-400 animate-pulse'
                    : isCooling
                      ? 'bg-amber-500'
                      : account.auth_status === 'connected'
                        ? 'bg-green-500'
                        : 'bg-gray-400'
                }`}
              />

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {account.email || account.id}
                  </span>
                  {isCooling && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">
                      Cooldown
                    </span>
                  )}
                  {account.last_error_code === '429' && !isCooling && account.auth_status === 'connected' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                      Recovered
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-gray-400 dark:text-gray-500 font-mono">{account.id}</span>
                <div className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">
                  {isCooling
                    ? `Backend cooldown resets ${formatServerDateTime(account.cooldown_until)} (${formatTimeRemaining(account.cooldown_until)})`
                    : account.last_error_code === '429'
                      ? 'Previous 429 cleared; backend cooldown is inactive.'
                      : account.auth_status === 'connected'
                        ? 'Available now for pool rotation.'
                        : 'Authenticate this account before it can join the pool.'}
                </div>
              </div>

              <div className="flex items-center gap-1.5 flex-shrink-0">
                {account.auth_status !== 'connected' && !isPending && (
                  <button
                    type="button"
                    onClick={() => onConnectAccount(account.id)}
                    className="text-[11px] px-2 py-1 rounded border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                  >
                    Connect
                  </button>
                )}
                {isPending && (
                  <span className="text-[11px] text-amber-600 dark:text-amber-400 animate-pulse">
                    Waiting...
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => onToggleEnabled(account.id, !account.pool_enabled)}
                  title={account.pool_enabled ? 'Disable' : 'Enable'}
                  className={`w-8 h-4 rounded-full relative transition-colors ${
                    account.pool_enabled ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${
                      account.pool_enabled ? 'left-[18px]' : 'left-0.5'
                    }`}
                  />
                </button>
                <button
                  type="button"
                  onClick={() => onRemoveAccount(account.id)}
                  className="text-[11px] px-1.5 py-1 rounded text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                  title="Remove"
                >
                  ✕
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={onAddAccount}
        disabled={addingAccount}
        className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
      >
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
        </svg>
        {addingAccount ? 'Adding...' : 'Add Google Account'}
      </button>
    </>
  );
}
