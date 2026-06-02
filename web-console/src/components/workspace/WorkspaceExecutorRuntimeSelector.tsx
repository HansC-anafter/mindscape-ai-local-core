'use client';

import React from 'react';

import {
  deriveWorkspaceExecutorRuntimeOptions,
  deriveWorkspaceExecutorRuntimeStatus,
  type WorkspaceExecutorAgentInfo,
} from './workspaceExecutorRuntimeViewModel';

interface WorkspaceExecutorRuntimeSelectorProps {
  agents: WorkspaceExecutorAgentInfo[];
  routeEntries: string[];
  resolvedRuntime: string | null;
  selectedRuntimeId: string | null;
  disabled: boolean;
  onSelect: (runtimeId: string | null) => void;
  layout: 'inline' | 'panel';
}

export function WorkspaceExecutorRuntimeSelector({
  agents,
  routeEntries,
  resolvedRuntime,
  selectedRuntimeId,
  disabled,
  onSelect,
  layout,
}: WorkspaceExecutorRuntimeSelectorProps) {
  const options = deriveWorkspaceExecutorRuntimeOptions(routeEntries, resolvedRuntime, agents);
  const status = deriveWorkspaceExecutorRuntimeStatus(
    selectedRuntimeId,
    routeEntries,
    resolvedRuntime,
    agents,
  );
  const selectClassName = layout === 'panel'
    ? 'w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900'
    : 'max-w-full rounded-[16px] border border-[#c7af7d] bg-white/95 px-2 py-1 text-xs text-slate-900 shadow-[0_6px_14px_rgba(166,139,94,0.10)] outline-none transition focus:border-[#9b7a3a] focus:ring-2 focus:ring-[#d3b57a]/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-700';
  const badgeClassName = status.badgeLabel === 'available'
    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
    : status.badgeLabel === 'bound'
      ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300'
      : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

  const statusText = (
    <>
      {status.statusLabel}
      {status.reason ? ` - ${status.reason}` : ''}
    </>
  );

  return (
    <div
      className={layout === 'panel' ? 'space-y-3' : 'flex min-w-0 flex-wrap items-center gap-2'}
      data-testid="workspace-executor-runtime-selector"
    >
      {layout === 'panel' ? (
        <div className="rounded border border-gray-200 p-2 text-xs dark:border-gray-800">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
                Active Runtime
              </div>
              <div className="mt-1 truncate text-sm font-semibold leading-5 text-gray-900 dark:text-gray-100">
                {status.name}
              </div>
            </div>
            <span className={`mt-0.5 inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] ${badgeClassName}`}>
              {status.badgeLabel}
            </span>
          </div>
          <div className="mt-2 text-[11px] leading-5 text-gray-500 dark:text-gray-400">
            {statusText}
          </div>
        </div>
      ) : null}

      <div className={layout === 'panel' ? 'space-y-1.5' : 'min-w-0'}>
        {layout === 'panel' ? (
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">
            Runtime
          </div>
        ) : null}
        <select
          aria-label="Workspace Executor"
          className={selectClassName}
          disabled={disabled}
          title="Select Agent"
          value={selectedRuntimeId || ''}
          onChange={(event) => onSelect(event.target.value || null)}
        >
          <option value="">Mindscape LLM</option>
          {options.map((option) => (
            <option key={option.id} value={option.id} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {layout === 'inline' ? (
        <div className="flex min-w-0 items-center gap-2 text-xs text-gray-500 dark:text-gray-300">
          <span className="truncate">{statusText}</span>
        </div>
      ) : null}
    </div>
  );
}
