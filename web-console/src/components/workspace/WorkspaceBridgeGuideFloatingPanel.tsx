'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, Copy, PlayCircle, RefreshCw, RotateCw } from 'lucide-react';

import { WorkspaceFloatingSettingsPanel } from './WorkspaceFloatingSettingsPanel';

interface WorkspaceBridgeGuideFloatingPanelProps {
  open: boolean;
  workspaceId: string;
  apiUrl: string;
  bridgeScriptPath?: string | null;
  onBridgeServiceChanged?: () => void;
  onClose: () => void;
}

interface BridgeServiceSnapshot {
  state?: string | null;
  running?: boolean | null;
  installed?: boolean | null;
  supported?: boolean | null;
  auto_recovery?: boolean | null;
  message?: string | null;
  reason?: string | null;
  plist_path?: string | null;
  label?: string | null;
}

interface CommandRowProps {
  label: string;
  command: string;
}

function CommandRow({ label, command }: CommandRowProps) {
  const [copied, setCopied] = useState(false);

  const copyCommand = async () => {
    await navigator.clipboard.writeText(command);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="space-y-1 rounded border border-gray-200 p-3 dark:border-gray-800">
      <div className="text-xs font-semibold text-gray-700 dark:text-gray-300">{label}</div>
      <div className="flex items-start gap-2">
        <pre className="min-w-0 flex-1 overflow-x-auto whitespace-pre-wrap break-all rounded bg-gray-950 p-2 text-xs text-emerald-300">
          {command}
        </pre>
        <button
          type="button"
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
          aria-label={`Copy ${label}`}
          onClick={() => void copyCommand()}
        >
          {copied ? <Check aria-hidden="true" className="h-4 w-4" /> : <Copy aria-hidden="true" className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

function normalizeApiUrl(value: string): string {
  return value.replace(/\/+$/, '');
}

function bridgeStateLabel(snapshot: BridgeServiceSnapshot | null, loading: boolean): string {
  if (loading && !snapshot) return 'Checking';
  if (!snapshot) return 'Unchecked';
  if (snapshot.running || snapshot.state === 'ready') return 'Ready';
  if (snapshot.state === 'device_node_unavailable') return 'Device Node offline';
  if (snapshot.state === 'unsupported_tool') return 'Update Device Node';
  if (snapshot.state === 'not_installed') return 'Not installed';
  if (snapshot.state === 'recovering') return 'Recovering';
  return snapshot.state || 'Unavailable';
}

function bridgeStateClass(snapshot: BridgeServiceSnapshot | null): string {
  if (snapshot?.running || snapshot?.state === 'ready') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300';
  }
  if (snapshot?.state === 'device_node_unavailable' || snapshot?.state === 'control_failed') {
    return 'border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300';
  }
  return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300';
}

export function WorkspaceBridgeGuideFloatingPanel({
  open,
  workspaceId,
  apiUrl,
  bridgeScriptPath,
  onBridgeServiceChanged,
  onClose,
}: WorkspaceBridgeGuideFloatingPanelProps) {
  const unixBridgeScript = bridgeScriptPath || './scripts/start_cli_bridge.sh';
  const [bridgeStatus, setBridgeStatus] = useState<BridgeServiceSnapshot | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<'start' | 'restart' | null>(null);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const bridgeServiceBase = useMemo(
    () => `${normalizeApiUrl(apiUrl)}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/agents/bridge-service`,
    [apiUrl, workspaceId],
  );

  const refreshBridgeStatus = useCallback(async () => {
    if (!open) return;
    setStatusLoading(true);
    setServiceError(null);
    try {
      const response = await fetch(bridgeServiceBase, { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(`Bridge service status failed: ${response.status}`);
      }
      setBridgeStatus(await response.json());
    } catch (error) {
      setServiceError(error instanceof Error ? error.message : 'Bridge service status failed');
    } finally {
      setStatusLoading(false);
    }
  }, [bridgeServiceBase, open]);

  useEffect(() => {
    if (!open) return;
    void refreshBridgeStatus();
  }, [open, refreshBridgeStatus]);

  const runBridgeAction = async (action: 'start' | 'restart') => {
    setActionLoading(action);
    setServiceError(null);
    try {
      const response = await fetch(`${bridgeServiceBase}/${action}`, {
        method: 'POST',
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error(`Bridge service ${action} failed: ${response.status}`);
      }
      setBridgeStatus(await response.json());
      onBridgeServiceChanged?.();
    } catch (error) {
      setServiceError(error instanceof Error ? error.message : `Bridge service ${action} failed`);
    } finally {
      setActionLoading(null);
    }
  };
  const startDisabled = Boolean(actionLoading) || bridgeStatus?.state === 'device_node_unavailable' || bridgeStatus?.state === 'unsupported_tool';

  return (
    <WorkspaceFloatingSettingsPanel
      open={open}
      title="Workspace CLI Bridge"
      closeLabel="Close CLI Bridge Guide"
      onClose={onClose}
    >
      <div className="space-y-4">
        <div className="rounded border border-gray-200 p-3 text-sm dark:border-gray-800">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="font-semibold text-gray-900 dark:text-gray-100">LaunchAgent supervisor</div>
              <div className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
                The macOS plist keeps the shared CLI bridge supervisor alive across crashes and restarts.
              </div>
            </div>
            <span className={`shrink-0 rounded border px-2 py-1 text-xs font-semibold ${bridgeStateClass(bridgeStatus)}`}>
              {bridgeStateLabel(bridgeStatus, statusLoading)}
            </span>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <button
              type="button"
              className="inline-flex items-center justify-center gap-2 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300 dark:hover:bg-emerald-950/50"
              disabled={startDisabled}
              onClick={() => void runBridgeAction('start')}
            >
              <PlayCircle aria-hidden="true" className="h-4 w-4" />
              {actionLoading === 'start' ? 'Starting...' : 'Start Bridge'}
            </button>
            <button
              type="button"
              className="inline-flex items-center justify-center gap-2 rounded border border-gray-200 px-3 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
              disabled={Boolean(actionLoading)}
              onClick={() => void runBridgeAction('restart')}
            >
              <RotateCw aria-hidden="true" className="h-4 w-4" />
              {actionLoading === 'restart' ? 'Restarting...' : 'Restart'}
            </button>
            <button
              type="button"
              className="inline-flex items-center justify-center gap-2 rounded border border-gray-200 px-3 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
              disabled={statusLoading || Boolean(actionLoading)}
              onClick={() => void refreshBridgeStatus()}
            >
              <RefreshCw aria-hidden="true" className={`h-4 w-4 ${statusLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
          <div className="mt-3 rounded border border-gray-200 p-2 text-xs text-gray-600 dark:border-gray-800 dark:text-gray-300">
            {bridgeStatus?.message || 'Bridge service status has not been checked yet.'}
            {bridgeStatus?.auto_recovery ? (
              <span className="ml-1 font-semibold text-emerald-700 dark:text-emerald-300">Auto-recovery enabled.</span>
            ) : null}
            {bridgeStatus?.plist_path ? (
              <div className="mt-1 break-all text-gray-500 dark:text-gray-400">{bridgeStatus.plist_path}</div>
            ) : null}
          </div>
          {serviceError ? (
            <div className="mt-3 flex items-start gap-2 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
              <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{serviceError}</span>
            </div>
          ) : null}
        </div>

        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500 dark:text-gray-400">Manual fallback</div>
          <CommandRow label="macOS / Linux all workspaces" command={`${unixBridgeScript} --all`} />
          <CommandRow label="macOS / Linux current workspace" command={`${unixBridgeScript} --workspace-id ${workspaceId}`} />
          <CommandRow label="Windows all workspaces" command=".\\scripts\\start_cli_bridge.ps1 -All" />
          <CommandRow label="Windows current workspace" command={`.\\scripts\\start_cli_bridge.ps1 -WorkspaceId ${workspaceId}`} />
        </div>
      </div>
    </WorkspaceFloatingSettingsPanel>
  );
}
